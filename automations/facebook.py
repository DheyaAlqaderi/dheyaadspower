"""
FacebookWorker - Specialized in Automated Facebook Post / Reel Comment Monitoring,
Public Replies, and Messenger Private Direct Messaging.

Features:
1. Automatically switches comment sorting from "Most relevant" (الأبرز) to "All comments" (كل التعليقات).
2. Robust Language-Agnostic comment extraction (excludes main post, extracts author via profile links, extracts comment text and IDs).
3. Deterministic SHA-256 / comment_id tracking with persistent per-profile disk storage (facebook_history_{profile_id}.json).
4. Prevents duplicate replies: checks if our Page already replied in the comment branch.
5. Supports customizable action_type: 'reply_and_dm', 'public_reply_only', 'dm_only'.
6. Handles public replies via Lexical/Draft.js inputs with human keystrokes simulation.
7. Handles private Messenger DMs via "Send message" / "إرسال رسالة" and safely closes the floating chat dock afterwards.
8. Soft pagination: clicks "View more comments" / "عرض المزيد من التعليقات" and expands replies without destructive page refreshes.
9. Per-user cooldown support (cooldown_hours) and hourly rate limiting (max_replies_per_hour).
10. Action block / restriction shield: detects Facebook warning modals and halts safely.
11. Dynamic live configuration reload on each cycle without requiring worker restarts.
"""

import os
import re
import json
import time
import random
import hashlib
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple, Set
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from automations.base import BaseAutomationWorker

# --------------------------------------------------------------------------
# JAVASCRIPT HELPERS FOR FACEBOOK
# --------------------------------------------------------------------------

# JS to switch comment sorting from "Most Relevant" to "All Comments"
# JS to switch comment sorting from "Most Relevant" to "Newest" or "All Comments"
SWITCH_COMMENT_SORTING_JS = r"""
function switchCommentSorting() {
    // 1. Search for sorting dropdown trigger
    const buttons = Array.from(document.querySelectorAll('div[role="button"], span[role="button"], a[role="button"]'));
    const sortBtn = buttons.find(b => {
        if (!b.offsetParent && b.offsetHeight === 0) return false;
        const txt = (b.innerText || '').toLowerCase().trim();
        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
        const combined = txt + ' ' + aria;
        const isMostRelevant = combined.includes('most relevant') || combined.includes('الأبرز') || combined.includes('أبرز التعليقات');
        const isNewestOrAll = combined.includes('newest') || combined.includes('الأحدث') || combined.includes('all comments') || combined.includes('كل التعليقات');
        return isMostRelevant && !isNewestOrAll;
    });

    if (sortBtn) {
        sortBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
        sortBtn.click();
        return { needSwitch: true, current: sortBtn.innerText };
    }

    return { needSwitch: false };
}
return switchCommentSorting();
"""

# JS to unconditionally open the comment filter dropdown (even if already on Newest / All Comments)
OPEN_COMMENT_FILTER_DROPDOWN_JS = r"""
function openCommentFilterDropdown() {
    const isVisible = (e) => {
        if (!e) return false;
        return !!(e.offsetWidth > 0 || e.offsetHeight > 0 || (e.getClientRects && e.getClientRects().length > 0));
    };

    // 1. If a visible menu is already open, do not toggle-close it!
    const menus = Array.from(document.querySelectorAll('div[role="menu"]'));
    const existingMenu = menus.find(m => isVisible(m));
    if (existingMenu) {
        const mTxt = (existingMenu.innerText || '').toLowerCase();
        if (mTxt.includes('newest') || mTxt.includes('الأحدث') || mTxt.includes('all comments') || mTxt.includes('most relevant')) {
            return { clicked: true, alreadyOpen: true };
        }
    }

    const buttons = Array.from(document.querySelectorAll('div[role="button"], span[role="button"], a[role="button"], button'));
    
    let sortBtn = buttons.find(b => {
        if (!isVisible(b)) return false;
        const txt = (b.innerText || '').toLowerCase().trim();
        const aria = (b.getAttribute('aria-label') || '').toLowerCase().trim();
        const combined = txt + ' ' + aria;

        if (combined.includes('like') || combined.includes('إعجاب') ||
            combined.includes('reply') || combined.includes('رد') ||
            combined.includes('send') || combined.includes('إرسال') ||
            combined.includes('share') || combined.includes('مشاركة') ||
            combined.includes('close') || combined.includes('إغلاق') ||
            combined.includes('back') || combined.includes('رجوع')) {
            return false;
        }

        return (
            combined.includes('newest') || combined.includes('الأحدث') ||
            combined.includes('all comments') || combined.includes('كل التعليقات') || combined.includes('جميع التعليقات') ||
            combined.includes('most relevant') || combined.includes('الأبرز') || combined.includes('أبرز التعليقات') ||
            combined.includes('comment ordering') || combined.includes('ترتيب التعليقات') ||
            (b.getAttribute('aria-haspopup') === 'menu' && (combined.includes('comment') || combined.includes('تعليق')))
        );
    });

    if (!sortBtn) {
        // Fallback: search spans/divs with exact sorting texts
        const spans = Array.from(document.querySelectorAll('span, div[dir="auto"]'));
        const hit = spans.find(s => {
            if (!isVisible(s)) return false;
            const t = (s.innerText || '').toLowerCase().trim();
            return (t === 'most relevant' || t === 'newest' || t === 'all comments' ||
                    t === 'الأبرز' || t === 'الأحدث' || t === 'كل التعليقات' ||
                    t === 'أبرز التعليقات' || t === 'أحدث التعليقات' || t === 'جميع التعليقات');
        });
        if (hit) {
            sortBtn = hit.closest('[role="button"], button, div[tabindex="0"]') || hit;
        }
    }

    if (sortBtn) {
        const clickTarget = sortBtn.closest('[role="button"], button') || sortBtn;
        clickTarget.scrollIntoView({ block: 'center', behavior: 'instant' });
        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
            clickTarget.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
        });
        try { clickTarget.click(); } catch(e) {}
        return { clicked: true, text: (sortBtn.innerText || sortBtn.getAttribute('aria-label') || '').trim() };
    }

    return { clicked: false };
}
return openCommentFilterDropdown();
"""

# JS to select "Newest" (or "All comments") item from the opened sorting menu
SELECT_NEWEST_MENUITEM_JS = r"""
function selectNewestMenuItem() {
    const isVisible = (e) => {
        if (!e) return false;
        return !!(e.offsetWidth > 0 || e.offsetHeight > 0 || (e.getClientRects && e.getClientRects().length > 0));
    };

    // Find the visible menu container (the latest opened popover in DOM)
    const visibleMenus = Array.from(document.querySelectorAll('div[role="menu"], div[data-visualcompletion="ignore-dynamic-extra"]')).filter(m => isVisible(m));
    const menu = visibleMenus[visibleMenus.length - 1] || document.querySelector('div[role="menu"]') || document;
    
    // Collect specific candidate rows/buttons (excluding broad wrappers)
    const candidates = Array.from(menu.querySelectorAll(
        'div[role="menuitemradio"], div[role="menuitem"], div[role="button"], div[tabindex="0"], div.x1i10hfl, span, div'
    ));

    // Priority 1: Specifically find "Newest" / "الأحدث"
    let target = candidates.find(el => {
        if (!isVisible(el)) return false;
        const txt = (el.innerText || '').toLowerCase().trim();
        const aria = (el.getAttribute('aria-label') || '').toLowerCase().trim();
        
        // Must contain "newest" or "الأحدث"
        const isNewest = txt.includes('newest') || txt.includes('الأحدث') || aria.includes('newest') || aria.includes('الأحدث');
        if (!isNewest) return false;

        // Must NOT contain other menu items (to avoid container elements)
        if (txt.includes('most relevant') || txt.includes('الأبرز') || txt.includes('أبرز') ||
            txt.includes('all comments') || txt.includes('كل التعليقات') ||
            txt.includes('hidden by this page') || txt.includes('تم إخفاؤه')) {
            return false;
        }

        // Must be concise item text (not the entire menu body)
        if (txt.length > 250) return false;

        return true;
    });

    // Priority 2: Find exact text span for "Newest" / "الأحدث"
    if (!target) {
        const spans = Array.from(menu.querySelectorAll('span, div[dir="auto"]'));
        const exactSpan = spans.find(s => {
            if (!isVisible(s)) return false;
            const t = (s.innerText || '').trim().toLowerCase();
            return (t === 'newest' || t === 'الأحدث' || t === 'newest comments' || t === 'أحدث التعليقات') && !t.includes('\n');
        });
        if (exactSpan) {
            target = exactSpan.closest('div[role="menuitemradio"], div[role="menuitem"], div[role="button"], div[tabindex="0"]') || exactSpan;
        }
    }

    // Priority 3: Match by description "with the newest comments first" / "أحدث التعليقات أولاً"
    if (!target) {
        const all = Array.from(menu.querySelectorAll('*'));
        const descEl = all.find(el => {
            if (!isVisible(el)) return false;
            const t = (el.innerText || '').toLowerCase().trim();
            return (t.includes('newest comments first') || t.includes('أحدث التعليقات أولاً') || t.includes('newest first')) &&
                   !t.includes('most relevant') && !t.includes('الأبرز') && !t.includes('أبرز') && t.length < 250;
        });
        if (descEl) {
            target = descEl.closest('div[role="menuitemradio"], div[role="menuitem"], div[role="button"], div[tabindex="0"]') || descEl;
        }
    }

    // Priority 4: Fallback to "All comments" / "كل التعليقات" if Newest is not available
    if (!target) {
        target = candidates.find(el => {
            if (!isVisible(el)) return false;
            const txt = (el.innerText || '').toLowerCase().trim();
            const aria = (el.getAttribute('aria-label') || '').toLowerCase().trim();
            const hasAll = txt.includes('all comments') || txt.includes('كل التعليقات') || aria.includes('all comments') || aria.includes('كل التعليقات');
            return hasAll && !txt.includes('most relevant') && !txt.includes('الأبرز') && !txt.includes('أبرز') && txt.length < 250;
        });
    }

    if (target) {
        const clickItem = target.closest('div[role="menuitemradio"], div[role="menuitem"], div[role="button"], div[tabindex="0"]') || target;
        clickItem.scrollIntoView({ block: 'center', behavior: 'instant' });
        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
            clickItem.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
        });
        try { clickItem.click(); } catch(e) {}
        return { success: true, text: (clickItem.innerText || clickItem.getAttribute('aria-label') || '').trim().split('\n')[0] };
    }

    return { success: false };
}
return selectNewestMenuItem();
"""

# JS to find and click the Send message button inside the Facebook private reply modal dialog
FIND_AND_CLICK_DM_SEND_BUTTON_JS = r"""
function findAndClickDmSendButton() {
    // 1. Locate active dialog or modal
    const dialogs = Array.from(document.querySelectorAll('div[role="dialog"], div[aria-modal="true"]'));
    const dialog = dialogs.find(d => {
        if (!d.offsetParent && d.offsetHeight === 0) return false;
        const txt = (d.innerText || '').toLowerCase();
        const aria = (d.getAttribute('aria-label') || '').toLowerCase();
        return aria.includes('message') || aria.includes('رسالة') ||
               txt.includes('send a private reply') || txt.includes('messenger') || txt.includes('خاص');
    }) || dialogs.find(d => d.offsetParent || d.offsetHeight > 0) || document;

    // 2. Find all buttons inside this dialog
    const buttons = Array.from(dialog.querySelectorAll('div[role="button"], button'));
    const sendBtn = buttons.find(b => {
        const aria = (b.getAttribute('aria-label') || '').toLowerCase().trim();
        const text = (b.innerText || '').toLowerCase().trim();

        // Exclude close, go back, and other unrelated buttons
        if (aria.includes('close') || aria.includes('إغلاق') || 
            aria.includes('back') || aria.includes('رجوع') ||
            text.includes('close') || text.includes('إغلاق') ||
            text.includes('go back') || text.includes('الرجوع')) {
            return false;
        }

        return (
            aria === 'send message' || aria === 'إرسال رسالة' ||
            aria === 'send' || aria === 'إرسال' ||
            aria.includes('send message') || aria.includes('إرسال رسالة') ||
            text === 'send message' || text === 'إرسال رسالة' ||
            text.includes('send message') || text.includes('إرسال رسالة') ||
            text === 'send' || text === 'إرسال'
        );
    });

    if (!sendBtn) {
        return { clicked: false, reason: "button_not_found" };
    }

    // Force enable if still disabled in React state
    sendBtn.removeAttribute('aria-disabled');
    sendBtn.removeAttribute('disabled');
    sendBtn.scrollIntoView({ block: 'center', behavior: 'instant' });

    // Fire complete mouse event sequence
    const mouseEvents = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
    mouseEvents.forEach(type => {
        sendBtn.dispatchEvent(new MouseEvent(type, {
            bubbles: true,
            cancelable: true,
            view: window
        }));
    });

    try {
        sendBtn.click();
    } catch(e) {}

    return {
        clicked: true,
        label: sendBtn.getAttribute('aria-label') || sendBtn.innerText
    };
}
return findAndClickDmSendButton();
"""

# JS to expand older comments ("View more comments") and replies smoothly inside nested scroll container
CLICK_EXPAND_COMMENTS_JS = r"""
function expandMoreComments() {
    function getScrollContainer() {
        const ref = document.querySelector('div[role="article"]') ||
                    document.querySelector('div[data-ad-rendering-role="story_message"]') ||
                    document.querySelector('form');
        if (ref) {
            let el = ref.parentElement;
            while (el && el !== document.body && el !== document.documentElement) {
                const cs = window.getComputedStyle(el);
                const oy = cs.overflowY;
                if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 20) {
                    return el;
                }
                el = el.parentElement;
            }
        }
        const candidates = Array.from(document.querySelectorAll('div.xq1qtft, div.xb57i2i, div[role="dialog"], div[role="main"]'));
        for (const c of candidates) {
            const cs = window.getComputedStyle(c);
            const oy = cs.overflowY;
            if ((oy === 'auto' || oy === 'scroll') && c.scrollHeight > c.clientHeight + 20) {
                return c;
            }
        }
        return document.scrollingElement || document.documentElement || document.body;
    }

    const scroller = getScrollContainer();
    const searchRoot = (scroller && scroller !== document.body && scroller !== document.documentElement) ? scroller : document;
    const buttons = Array.from(searchRoot.querySelectorAll('div[role="button"], span[role="button"], a[role="button"]'));
    let clickedCount = 0;

    for (const b of buttons) {
        if (!b.offsetParent && b.offsetHeight === 0) continue;
        const txt = (b.innerText || '').toLowerCase().trim();
        const aria = (b.getAttribute('aria-label') || '').toLowerCase().trim();
        const combined = txt + ' ' + aria;

        const isMoreComments = (
            combined.includes('view more comments') || combined.includes('view previous comments') ||
            combined.includes('view older comments') || combined.includes('view next comments') ||
            combined.includes('عرض المزيد من التعليقات') || combined.includes('عرض التعليقات السابقة') ||
            combined.includes('عرض مزيد من التعليقات') ||
            (combined.includes('comments') && (combined.includes('more') || combined.includes('previous')) && !combined.includes('hide')) ||
            (combined.includes('تعليق') && (combined.includes('مزيد') || combined.includes('سابق')) && !combined.includes('إخفاء'))
        );

        const isMoreReplies = (
            (combined.includes('view') && (combined.includes('reply') || combined.includes('replies'))) ||
            (combined.includes('عرض') && (combined.includes('رد') || combined.includes('ردود')))
        );

        if (isMoreComments || isMoreReplies) {
            b.scrollIntoView({ block: 'center', behavior: 'instant' });
            b.click();
            clickedCount++;
            if (clickedCount >= 3) break;
        }
    }

    let scrolled = false;
    if (scroller && scroller !== document.body && scroller !== document.documentElement) {
        scroller.scrollBy({ top: 500, behavior: 'smooth' });
        scrolled = true;
    } else {
        window.scrollBy({ top: 500, behavior: 'smooth' });
        scrolled = true;
    }

    return { clicked: clickedCount, scrolled: scrolled };
}
return expandMoreComments();
"""

# JS to extract structured comment objects from modern Facebook DOM
EXTRACT_COMMENTS_JS = r"""
function extractFacebookComments(pageNameFilter) {
    const lowerPageName = (pageNameFilter || '').toLowerCase().trim();
    const articles = Array.from(document.querySelectorAll('div[role="article"]'));
    const comments = [];
    const seenCids = new Set();

    function isTimestampString(txt) {
        if (!txt) return false;
        const t = txt.toLowerCase().trim();
        if (/^\d+\s*[smhdw]$/i.test(t)) return true;
        if (/^\d+\s*(?:second|minute|hour|day|week|month|year)s?(?:\s+ago)?$/i.test(t)) return true;
        if (/^(?:just now|a few seconds ago|a few seconds|about a minute ago|about a minute|yesterday|today|الآن|منذ|قبل)/i.test(t)) return true;
        if (/(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|يناير|فبراير|مارس|أبريل|مايو|يونيو|يوليو|أغسطس|سبتمبر|أكتوبر|نوفمبر|ديسمبر)/i.test(t)) return true;
        return false;
    }

    function cleanAuthorName(name) {
        if (!name) return '';
        let s = name.trim();
        // Remove leading prefixes
        s = s.replace(/^(?:Comment by|تعليق من|Reply by|رد من)\s+/i, '');
        // Remove trailing relative timestamps in English and Arabic
        s = s.replace(/\s+(?:a few seconds|about a minute|just now|\d+\s*(?:seconds?|minutes?|hours?|days?|weeks?|m|h|d|s|min|hr)|yesterday|today)(?:\s+ago)?.*$/i, '');
        s = s.replace(/\s+(?:منذ|قبل)\s+(?:بضع ثوان|ثوانٍ|دقيقة|دقائق|ساعة|ساعات|يوم|أيام|أمس|الآن).*$/, '');
        return s.trim();
    }

    // PASS 1: Detect all authors who have ALREADY been replied to by our Page on this entire post
    const authorsRepliedOnPost = new Set();

    for (let i = 0; i < articles.length; i++) {
        const art = articles[i];
        if (!art.offsetParent && art.offsetHeight === 0) continue;
        const ariaLabel = (art.getAttribute('aria-label') || '').toLowerCase();
        const fullText = (art.innerText || '').toLowerCase();

        const isOurReply = lowerPageName && (
            ariaLabel.includes(`reply by ${lowerPageName}`) ||
            ariaLabel.includes(`رد من ${lowerPageName}`) ||
            fullText.startsWith(lowerPageName) ||
            fullText.includes(` ${lowerPageName} `)
        );
        const hasPrivateReplyNotice = (
            fullText.includes('page replied privately') ||
            fullText.includes('ردت الصفحة بشكل خاص') ||
            ariaLabel.includes('page replied privately') ||
            ariaLabel.includes('ردت الصفحة بشكل خاص')
        );

        if (isOurReply || hasPrivateReplyNotice) {
            const thread = art.closest('.x18xomjl') || art.closest('.xbcz3fp') || art.parentElement.closest('div.html-div') || art.parentElement;
            if (thread) {
                const threadArticles = Array.from(thread.querySelectorAll('div[role="article"]'));
                for (const ta of threadArticles) {
                    const taLinks = Array.from(ta.querySelectorAll('a[role="link"], a[href*="facebook.com"], a[href^="/"]'));
                    let taAuthor = '';
                    for (const l of taLinks) {
                        const href = l.getAttribute('href') || '';
                        const linkTxt = (l.innerText || '').trim();
                        if (linkTxt && !isTimestampString(linkTxt) && !href.includes('/hashtag/') && !href.includes('/photo') && linkTxt.length < 60) {
                            if (!linkTxt.includes('Like') && !linkTxt.includes('Reply') && !linkTxt.includes('إعجاب') && !linkTxt.includes('رد') && !linkTxt.includes('Hide') && !linkTxt.includes('إخفاء')) {
                                taAuthor = cleanAuthorName(linkTxt);
                                break;
                            }
                        }
                    }
                    if (!taAuthor) {
                        const taLabel = (ta.getAttribute('aria-label') || '').trim();
                        if (taLabel) taAuthor = cleanAuthorName(taLabel);
                    }
                    if (taAuthor && (!lowerPageName || !taAuthor.toLowerCase().includes(lowerPageName))) {
                        authorsRepliedOnPost.add(taAuthor.toLowerCase().trim());
                    }
                }
            }
        }
    }

    // PASS 2: Extract structured comment objects
    for (let i = 0; i < articles.length; i++) {
        const art = articles[i];
        if (!art.offsetParent && art.offsetHeight === 0) continue;

        const ariaLabel = (art.getAttribute('aria-label') || '').trim();
        const ariaDesc = (art.getAttribute('aria-description') || '').trim();
        const fullText = (art.innerText || '').trim();

        // Verify this article is a COMMENT, not the main post
        const isCommentAria = (
            ariaLabel.toLowerCase().includes('comment by') || ariaLabel.toLowerCase().includes('تعليق من') ||
            ariaLabel.toLowerCase().includes('reply by') || ariaLabel.toLowerCase().includes('رد من') ||
            ariaDesc.toLowerCase().includes('comment') || ariaDesc.toLowerCase().includes('تعليق')
        );

        const buttons = Array.from(art.querySelectorAll('[role="button"], button'));
        const replyBtn = buttons.find(b => {
            const t = (b.innerText || '').toLowerCase().trim();
            const a = (b.getAttribute('aria-label') || '').toLowerCase().trim();
            return t === 'reply' || t === 'رد' || a === 'reply' || a === 'رد' ||
                   t.startsWith('reply') || t.startsWith('رد ');
        });

        if (!isCommentAria && !replyBtn) {
            continue;
        }

        // 1. Extract Author Name
        let author = '';
        let authorUrl = '';

        // Priority A: Search for author link inside comment
        const links = Array.from(art.querySelectorAll('a[role="link"], a[href*="facebook.com"], a[href^="/"]'));
        for (const l of links) {
            const href = l.getAttribute('href') || '';
            const linkTxt = (l.innerText || '').trim();
            if (linkTxt && !isTimestampString(linkTxt) && !href.includes('/hashtag/') && !href.includes('/photo') && linkTxt.length < 60) {
                if (!linkTxt.includes('Like') && !linkTxt.includes('Reply') && !linkTxt.includes('إعجاب') && !linkTxt.includes('رد') && !linkTxt.includes('Hide') && !linkTxt.includes('إخفاء')) {
                    author = cleanAuthorName(linkTxt);
                    authorUrl = href;
                    break;
                }
            }
        }

        // Priority B: Extract from aria-label
        if (!author && ariaLabel) {
            author = cleanAuthorName(ariaLabel);
        }

        // Priority C: Fallback to lines
        if (!author && fullText) {
            const lines = fullText.split('\n').map(s => s.trim()).filter(Boolean);
            if (lines.length > 0) {
                const first = lines[0];
                if (!['top fan', 'author', 'المؤلف', 'أبرز معجب'].includes(first.toLowerCase()) && !isTimestampString(first)) {
                    author = cleanAuthorName(first.slice(0, 40));
                } else if (lines.length > 1 && !isTimestampString(lines[1])) {
                    author = cleanAuthorName(lines[1].slice(0, 40));
                }
            }
        }

        if (!author) author = 'صديق';
        author = cleanAuthorName(author);

        // Filter out our own Page's comments
        if (lowerPageName && author.toLowerCase().includes(lowerPageName)) {
            continue;
        }

        // 2. Extract Comment Text (including emojis in img[alt])
        let commentText = '';
        const textContainers = Array.from(art.querySelectorAll('div[dir="auto"], span[dir="auto"]'));
        for (const tc of textContainers) {
            let t = (tc.innerText || '').trim();
            const imgs = Array.from(tc.querySelectorAll('img[alt]'));
            for (const img of imgs) {
                const alt = (img.getAttribute('alt') || '').trim();
                if (alt && !t.includes(alt) && !['Like', 'Love', 'Care', 'Haha', 'Wow', 'Sad', 'Angry', 'إعجاب'].includes(alt)) {
                    t = (t ? t + ' ' : '') + alt;
                }
            }
            t = t.trim();
            if (t && t !== author && !t.includes('Like') && !t.includes('Reply') && !t.includes('إعجاب') && !t.includes('رد')) {
                if (t.length > commentText.length) {
                    commentText = t;
                }
            }
        }
        if (!commentText) {
            commentText = fullText.slice(0, 150).replace(/\n+/g, ' ');
        }

        // 3. Extract Comment ID or permalink
        let commentId = '';
        for (const l of links) {
            const href = l.getAttribute('href') || '';
            const mNum = href.match(/comment_id=(\d+)/);
            if (mNum) {
                commentId = mNum[1];
                break;
            }
            const mAny = href.match(/comment_id=([^&]+)/);
            if (mAny && !commentId) {
                commentId = decodeURIComponent(mAny[1]);
            }
        }

        // 4. Check if our page has already replied in this comment thread or on this post
        let alreadyReplied = false;
        const authorLower = author.toLowerCase().trim();
        if (authorLower && authorsRepliedOnPost.has(authorLower)) {
            alreadyReplied = true;
        }

        const thread = art.closest('.x18xomjl') || art.closest('.xbcz3fp') || art.parentElement.closest('div.html-div') || art.parentElement;
        if (!alreadyReplied && lowerPageName && thread) {
            const articlesInThread = Array.from(thread.querySelectorAll('div[role="article"]'));
            for (const r of articlesInThread) {
                if (r === art) continue;
                const rAria = (r.getAttribute('aria-label') || '').toLowerCase();
                const rText = (r.innerText || '').toLowerCase();
                if (rAria.includes(`reply by ${lowerPageName}`) || rAria.includes(`رد من ${lowerPageName}`) ||
                    rText.includes(lowerPageName)) {
                    alreadyReplied = true;
                    break;
                }
            }
        }
        if (!alreadyReplied && fullText) {
            if (fullText.includes('Page replied privately') || fullText.includes('ردت الصفحة بشكل خاص')) {
                alreadyReplied = true;
            }
        }

        // 5. Detect "Send message" (DM) button
        const dmBtn = buttons.find(b => {
            const t = (b.innerText || '').toLowerCase().trim();
            const a = (b.getAttribute('aria-label') || '').toLowerCase().trim();
            return t.includes('send message') || t.includes('إرسال رسالة') ||
                   t.includes('message') || t.includes('مراسلة') ||
                   a.includes('send message') || a.includes('إرسال رسالة');
        });

        // Set a unique identifier key for this comment
        const uniqueKey = commentId ? `cid_${commentId}` : `txt_${author}_${commentText.slice(0, 50)}`;

        if (!seenCids.has(uniqueKey)) {
            seenCids.add(uniqueKey);
            comments.push({
                index: i,
                id: uniqueKey,
                commentId: commentId,
                author: author,
                authorUrl: authorUrl,
                text: commentText,
                alreadyReplied: alreadyReplied,
                userAlreadyRepliedOnPost: (authorLower && authorsRepliedOnPost.has(authorLower)),
                hasReplyButton: !!replyBtn,
                hasDmButton: !!dmBtn
            });
        }
    }

    return comments;
}
return extractFacebookComments(arguments[0]);
"""

# JS to detect Facebook rate limits, restrictions, or action blocked modals
CHECK_FB_RESTRICTIONS_JS = r"""
function checkFacebookRestrictions() {
    const dialogs = Array.from(document.querySelectorAll('div[role="dialog"], div[role="alertdialog"], div[role="alert"]'));
    const keywords = [
        'you’re temporarily blocked', "you're temporarily blocked",
        'action blocked', 'تم تقييدك مؤقتاً', 'حسابك مقيد مؤقتاً',
        'try again later', 'يرجى المحاولة لاحقاً', 'spam',
        'community standards', 'معايير المجتمع'
    ];

    for (const d of dialogs) {
        if (!d.offsetParent && d.offsetHeight === 0) continue;
        const txt = (d.innerText || '').toLowerCase();
        for (const kw of keywords) {
            if (txt.includes(kw.toLowerCase())) {
                return { detected: true, message: txt.slice(0, 150) };
            }
        }
    }

    return { detected: false };
}
return checkFacebookRestrictions();
"""

# JS to safely close or minimize floating Messenger chat docks/popups
CLOSE_MESSENGER_DOCK_JS = r"""
function closeMessengerDock() {
    // Target floating chat tabs at bottom right, NOT active modal dialogs
    const dockButtons = Array.from(document.querySelectorAll(
        'div[aria-label="Close chat"], div[aria-label="إغلاق الدردشة"], ' +
        'div[aria-label="إغلاق المحادثة"], ' +
        'div[data-pagelet*="ChatTab"] div[aria-label="Close"], ' +
        'div[data-pagelet*="ChatTab"] div[aria-label="إغلاق"], ' +
        'div.fbDock div[aria-label="Close"], div.fbDock div[aria-label="إغلاق"]'
    ));

    let closed = 0;
    for (const btn of dockButtons) {
        if (btn.offsetParent || btn.offsetHeight > 0) {
            btn.click();
            closed++;
        }
    }
    return { closed: closed };
}
return closeMessengerDock();
"""


class FacebookWorker(BaseAutomationWorker):
    """
    Worker specialized in automated Facebook post & reel monitoring,
    public comment replies, and direct Messenger replies.
    """

    def _get_history_filepath(self) -> str:
        """Returns the persistent JSON history path for this specific profile."""
        clean_id = "".join(c for c in str(self.profile_id) if c.isalnum() or c in ("-", "_"))
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), f"facebook_history_{clean_id}.json")

    def _load_history(self) -> Dict[str, float]:
        """Loads processed comment timestamps from disk."""
        filepath = self._get_history_filepath()
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return {str(k): float(v) for k, v in data.items()}
            except Exception as e:
                self.log("WARNING", f"خطأ أثناء قراءة سجل تعليقات فيسبوك: {e}")
        return {}

    def _save_history(self, history: Dict[str, float]) -> None:
        """Saves processed comments to disk atomically."""
        filepath = self._get_history_filepath()
        tmp = filepath + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            os.replace(tmp, filepath)
        except Exception as e:
            self.log("WARNING", f"خطأ أثناء حفظ سجل تعليقات فيسبوك: {e}")

    def _normalize_user_name(self, name: str) -> str:
        if not name:
            return ""
        s = name.strip()
        s = re.sub(r'^(?:Comment by|تعليق من|Reply by|رد من)\s+', '', s, flags=re.I)
        s = re.sub(r'\s+(?:a few seconds|about a minute|just now|\d+\s*(?:seconds?|minutes?|hours?|days?|weeks?|m|h|d|s|min|hr)|yesterday|today)(?:\s+ago)?.*$', '', s, flags=re.I)
        s = re.sub(r'\s+(?:منذ|قبل)\s+(?:بضع ثوان|ثوانٍ|دقيقة|دقائق|ساعة|ساعات|يوم|أيام|أمس|الآن).*$', '', s)
        return re.sub(r'\s+', ' ', s.lower().strip())

    def _extract_profile_id(self, url: str) -> str:
        if not url:
            return ""
        try:
            m = re.search(r'[?&]id=(\d+)', url)
            if m:
                return m.group(1)
            m = re.search(r'/user/(\d+)', url)
            if m:
                return m.group(1)
            m = re.search(r'facebook\.com/([a-zA-Z0-9\._\-]+)', url)
            if m:
                uname = m.group(1).lower()
                if uname not in ('groups', 'pages', 'share', 'hashtag', 'photo', 'watch', 'stories', 'permalink.php'):
                    return uname
        except Exception:
            pass
        return ""

    def _get_post_id(self, post_url: str) -> str:
        if not post_url:
            return "default_post"
        try:
            parsed = urllib.parse.urlparse(post_url.strip())
            qs = urllib.parse.parse_qs(parsed.query)
            if "story_fbid" in qs:
                return f"fbid_{qs['story_fbid'][0]}"
            if "fbid" in qs:
                return f"fbid_{qs['fbid'][0]}"
            path_parts = [p for p in parsed.path.strip("/").split("/") if p]
            if path_parts:
                candidate = path_parts[-1]
                if candidate and candidate not in ('posts', 'videos', 'reels', 'photos', 'share'):
                    return f"p_{candidate}"
                if len(path_parts) >= 2:
                    return f"p_{path_parts[-2]}_{candidate}"
        except Exception:
            pass
        clean_base = post_url.split("?")[0].rstrip("/")
        h = hashlib.sha256(clean_base.encode('utf-8')).hexdigest()[:12]
        return f"post_{h}"

    def _get_user_identifiers(self, author: str, author_url: str = "") -> List[str]:
        keys = []
        clean_name = self._normalize_user_name(author)
        if clean_name and clean_name not in ("صديق", "friend"):
            safe_name = re.sub(r'[\s\W]+', '_', clean_name).strip('_')
            if safe_name:
                keys.append(f"name_{safe_name}")
        if author_url:
            prof_id = self._extract_profile_id(author_url)
            if prof_id:
                keys.append(f"uid_{prof_id}")
        if not keys and author:
            safe_raw = re.sub(r'[\s\W]+', '_', author.strip().lower()).strip('_')
            if safe_raw:
                keys.append(f"raw_{safe_raw}")
        return keys

    def _is_user_done_on_post(self, post_id: str, author: str, author_url: str, history: Dict[str, float], action_type: str) -> bool:
        user_keys = self._get_user_identifiers(author, author_url)
        if not user_keys:
            return False
        for uk in user_keys:
            if f"post_{post_id}_{uk}_done" in history:
                return True
            pub_key = f"post_{post_id}_{uk}_public"
            dm_key = f"post_{post_id}_{uk}_dm"
            if action_type == "reply_and_dm":
                if pub_key in history and (dm_key in history or f"post_{post_id}_{uk}_dm_unavail" in history):
                    return True
            elif action_type == "public_reply_only":
                if pub_key in history:
                    return True
            elif action_type == "dm_only":
                if dm_key in history:
                    return True
        return False

    def _has_user_received_public(self, post_id: str, author: str, author_url: str, history: Dict[str, float]) -> bool:
        user_keys = self._get_user_identifiers(author, author_url)
        for uk in user_keys:
            if f"post_{post_id}_{uk}_public" in history or f"post_{post_id}_{uk}_done" in history:
                return True
        return False

    def _has_user_received_dm(self, post_id: str, author: str, author_url: str, history: Dict[str, float]) -> bool:
        user_keys = self._get_user_identifiers(author, author_url)
        for uk in user_keys:
            if f"post_{post_id}_{uk}_dm" in history or f"post_{post_id}_{uk}_done" in history:
                return True
        return False

    def _mark_user_action_on_post(self, post_id: str, author: str, author_url: str, history: Dict[str, float], action: str, timestamp: float) -> None:
        user_keys = self._get_user_identifiers(author, author_url)
        for uk in user_keys:
            history[f"post_{post_id}_{uk}_{action}"] = timestamp

    def execute(self):
        self._run_facebook()

    def _run_facebook(self):
        post_url = (self.config.get("post_url") or "https://www.facebook.com").strip()
        post_id = self._get_post_id(post_url)
        page_name = (self.config.get("page_name") or "DheyaStore").strip()
        public_tpl = (self.config.get("public_reply_template") or "أهلاً بك {name}! شكراً لتواصلك معنا، تم إرسال التفاصيل في الخاص 📩").strip()
        private_tpl = (self.config.get("private_dm_template") or "مرحباً {name}! نسعد بخدمتك دائماً بخصوص استفسارك على المنشور ✨").strip()
        action_type = self.config.get("action_type") or "reply_and_dm"  # 'reply_and_dm', 'public_reply_only', 'dm_only'
        check_interval = float(self.config.get("check_interval_seconds") or 45.0)
        cooldown_hours = float(self.config.get("cooldown_hours") if self.config.get("cooldown_hours") is not None else 24.0)
        max_replies_per_hour = int(self.config.get("max_replies_per_hour") or 30)

        # Load reply history from disk
        history = self._load_history()
        self._save_history(history)

        self.log("INFO", f"🚀 بدء تشغيل أتمتة فيسبوك للمنشور: {post_url[:70]}... [ID: {post_id}]")
        self.log("INFO", f"📄 اسم الصفحة المستهدفة: \"{page_name}\" | نوع الأتمتة: [{action_type}]")
        if cooldown_hours <= 0:
            self.log("INFO", "⏳ فترة الانتظار (Cooldown): معطلة (0 ساعة - الرد على جميع التعليقات الجديدة)")
        else:
            self.log("INFO", f"⏳ فترة الانتظار لنفس المستخدم (Cooldown): {cooldown_hours} ساعة")
        if history:
            self.log("INFO", f"💾 تم تحميل سجل التعليقات السابق: {len(history)} تعليق/مستخدم مسجل")

        # Navigate to target post
        self.status = "فتح رابط المنشور..."
        try:
            self.driver.get(post_url)
            self.sleep(random.uniform(5.0, 7.0))
        except Exception as e:
            self.log("ERROR", f"تعذر فتح رابط المنشور: {e}")
            return

        # Attempt to switch comment sorting to "All Comments"
        self._ensure_all_comments_sorted()

        reply_timestamps: List[float] = []
        consecutive_empty_cycles = 0

        while not self.stop_requested:
            # 1. Dynamic live configuration reload from disk
            try:
                meta_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "profiles_metadata.json")
                if os.path.exists(meta_path):
                    with open(meta_path, "r", encoding="utf-8") as mf:
                        all_meta = json.load(mf)
                        fb_cfg = all_meta.get(self.profile_id, {}).get("platforms", {}).get("facebook", {})
                        if fb_cfg:
                            if "public_reply_template" in fb_cfg and fb_cfg["public_reply_template"]:
                                public_tpl = fb_cfg["public_reply_template"].strip()
                            if "private_dm_template" in fb_cfg and fb_cfg["private_dm_template"]:
                                private_tpl = fb_cfg["private_dm_template"].strip()
                            if "page_name" in fb_cfg and fb_cfg["page_name"]:
                                page_name = fb_cfg["page_name"].strip()
                            if "action_type" in fb_cfg and fb_cfg["action_type"]:
                                action_type = fb_cfg["action_type"]
                            if "check_interval_seconds" in fb_cfg:
                                check_interval = float(fb_cfg["check_interval_seconds"])
                            if "max_replies_per_hour" in fb_cfg:
                                max_replies_per_hour = int(fb_cfg["max_replies_per_hour"])
                            if "cooldown_hours" in fb_cfg and fb_cfg["cooldown_hours"] is not None:
                                cooldown_hours = float(fb_cfg["cooldown_hours"])
            except Exception:
                pass

            # Prune hourly rate limit timestamps
            now = time.time()
            reply_timestamps[:] = [t for t in reply_timestamps if now - t < 3600]

            # Check rate limit
            if len(reply_timestamps) >= max_replies_per_hour:
                self.status = f"بلوغ سقف الردود ({max_replies_per_hour}/س)"
                self.log("WARNING", f"⚠️ تم الوصول للحد الأقصى للردود بالساعة ({max_replies_per_hour}). انتظار تبريد الأمان...")
                self.sleep(min(60.0, check_interval))
                continue

            # 2. Check Facebook action block or restrictions
            is_restricted, rest_msg = self._check_facebook_restrictions()
            if is_restricted:
                self.status = "تقييد مؤقت من فيسبوك"
                self.log("ERROR", f"🛑 توقف مؤقت بسبب تنبيه قيود فيسبوك: {rest_msg}")
                self.sleep(120.0)
                continue

            # 3. Soft pagination: expand more comments & replies
            self._expand_more_comments()

            # 4. Extract comments from DOM
            self.status = "فحص التعليقات..."
            extracted_comments = self._extract_comments(page_name)
            self.stats["comments_scanned"] = len(extracted_comments)

            # Pre-loop check: If ANY comment currently lacks interaction buttons,
            # re-click "Newest" in the filter to force Facebook to re-render comments with interactive buttons.
            missing_buttons = [c for c in extracted_comments if not c.get("hasReplyButton") and not c.get("hasDmButton")]
            if missing_buttons:
                self.log("INFO", f"🔄 تم رصد {len(missing_buttons)} تعليق بدون أزرار تفاعل: إعادة النقر على فلتر [الأحدث / Newest] لإظهار الأزرار...")
                if self._refresh_comments_filter_newest():
                    extracted_comments = self._extract_comments(page_name)
                    self.stats["comments_scanned"] = len(extracted_comments)

            action_taken_in_pass = 0

            for c in extracted_comments:
                if self.stop_requested:
                    break

                if len(reply_timestamps) >= max_replies_per_hour:
                    break

                cid = c.get("id") or ""
                author = c.get("author") or "صديق"
                author_url = c.get("authorUrl") or ""
                text_snippet = c.get("text") or ""
                already_replied_dom = c.get("alreadyReplied", False)
                user_already_replied_dom = c.get("userAlreadyRepliedOnPost", False)

                # 1. Deduplication check: in history
                if cid in history:
                    continue

                # 2. Check if DOM shows our Page already replied in this specific comment thread
                if already_replied_dom:
                    history[cid] = now
                    self._save_history(history)
                    continue

                # If DOM shows user was replied elsewhere on the post, check cooldown
                if user_already_replied_dom and cooldown_hours > 0:
                    self._mark_user_action_on_post(post_id, author, author_url, history, "done", now)
                    history[cid] = now
                    self._save_history(history)
                    continue

                # 3. Rule: Exactly 1 comment reply and 1 DM per user on this post
                if self._is_user_done_on_post(post_id, author, author_url, history, action_type):
                    self.log("INFO", f"⏳ تخطي تعليق جديد من [{author}]: تم الرد لمرة واحدة (عام وخاص) على هذا المستخدم مسبقاً على هذا المنشور.")
                    history[cid] = now
                    self._save_history(history)
                    continue

                # 4. Per-user cross-post cooldown check (only if cooldown_hours > 0)
                if cooldown_hours > 0:
                    user_keys = self._get_user_identifiers(author, author_url)
                    on_cooldown = False
                    for uk in user_keys:
                        ukey = f"user_{uk}"
                        if ukey in history:
                            last_time = history[ukey]
                            if now - last_time < cooldown_hours * 3600:
                                rem_hours = (cooldown_hours * 3600 - (now - last_time)) / 3600.0
                                self.log("INFO", f"⏳ تخطي تعليق ({author}): فترة انتظار التبريد نشطة (متبقي {rem_hours:.1f}س).")
                                history[cid] = now
                                self._save_history(history)
                                on_cooldown = True
                                break
                    if on_cooldown:
                        continue

                # Real-time comment check: If both reply and DM buttons are not yet visible,
                # attempt hover or wait for Facebook to finish mounting the actions toolbar
                if not c.get("hasReplyButton") and not c.get("hasDmButton"):
                    try:
                        recheck = self.driver.execute_script("""
                            const commentId = arguments[0];
                            const author = arguments[1];
                            const artIdx = arguments[2];
                            const articles = Array.from(document.querySelectorAll('div[role="article"]'));
                            let art = null;
                            if (commentId) {
                                art = articles.find(a => {
                                    const lks = Array.from(a.querySelectorAll('a[href*="comment_id="]'));
                                    return lks.some(l => (l.getAttribute('href') || '').includes(commentId));
                                });
                            }
                            if (!art && author) art = articles.find(a => (a.getAttribute('aria-label') || '').toLowerCase().includes(author.toLowerCase()));
                            if (!art && artIdx < articles.length) art = articles[artIdx];
                            if (!art) return { hasReply: false, hasDm: false };

                            // Dispatch hover events
                            art.scrollIntoView({ block: 'center', behavior: 'instant' });
                            art.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                            art.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));

                            const btns = Array.from(art.querySelectorAll('[role="button"], button'));
                            const r = btns.some(b => {
                                const t = (b.innerText || '').toLowerCase().trim();
                                const a = (b.getAttribute('aria-label') || '').toLowerCase().trim();
                                return t === 'reply' || t === 'رد' || a === 'reply' || a === 'رد' || t.startsWith('reply') || t.startsWith('رد ');
                            });
                            const d = btns.some(b => {
                                const t = (b.innerText || '').toLowerCase().trim();
                                const a = (b.getAttribute('aria-label') || '').toLowerCase().trim();
                                return t.includes('send message') || t.includes('إرسال رسالة') || a.includes('send message') || a.includes('إرسال رسالة');
                            });
                            return { hasReply: r, hasDm: d };
                        """, c.get("commentId"), author, c.get("index", 0))

                        if isinstance(recheck, dict):
                            c["hasReplyButton"] = recheck.get("hasReply", False)
                            c["hasDmButton"] = recheck.get("hasDm", False)
                    except Exception:
                        pass

                    # If STILL missing buttons, click "Newest" again in the filter to make them appear
                    if not c.get("hasReplyButton") and not c.get("hasDmButton"):
                        self.log("INFO", f"🔄 التعليق من [{author}] لا يحتوي على أزرار تفاعل: جاري إعادة النقر على فلتر [الأحدث / Newest] لإظهار الأزرار...")
                        if self._refresh_comments_filter_newest():
                            try:
                                recheck_newest = self.driver.execute_script("""
                                    const commentId = arguments[0];
                                    const author = arguments[1];
                                    const articles = Array.from(document.querySelectorAll('div[role="article"]'));
                                    let art = null;
                                    if (commentId) {
                                        art = articles.find(a => {
                                            const lks = Array.from(a.querySelectorAll('a[href*="comment_id="]'));
                                            return lks.some(l => (l.getAttribute('href') || '').includes(commentId));
                                        });
                                    }
                                    if (!art && author) art = articles.find(a => (a.getAttribute('aria-label') || '').toLowerCase().includes(author.toLowerCase()));
                                    if (!art) return { hasReply: false, hasDm: false };

                                    const btns = Array.from(art.querySelectorAll('[role="button"], button'));
                                    const r = btns.some(b => {
                                        const t = (b.innerText || '').toLowerCase().trim();
                                        const a = (b.getAttribute('aria-label') || '').toLowerCase().trim();
                                        return t === 'reply' || t === 'رد' || a === 'reply' || a === 'رد' || t.startsWith('reply') || t.startsWith('رد ');
                                    });
                                    const d = btns.some(b => {
                                        const t = (b.innerText || '').toLowerCase().trim();
                                        const a = (b.getAttribute('aria-label') || '').toLowerCase().trim();
                                        return t.includes('send message') || t.includes('إرسال رسالة') || a.includes('send message') || a.includes('إرسال رسالة');
                                    });
                                    return { hasReply: r, hasDm: d };
                                """, c.get("commentId"), author)

                                if isinstance(recheck_newest, dict):
                                    c["hasReplyButton"] = recheck_newest.get("hasReply", False)
                                    c["hasDmButton"] = recheck_newest.get("hasDm", False)
                            except Exception:
                                pass

                    if not c.get("hasReplyButton") and not c.get("hasDmButton"):
                        self.log("INFO", f"⏳ التعليق اللحظي من [{author}] قيد التجهيز في فيسبوك (أزرار الرد لم تكتمل بعد). سيتم فحصه بالدورة القادمة.")
                        continue
                    else:
                        self.log("SUCCESS", f"✅ ظهرت أزرار الرد والخاص بنجاح لتعليق [{author}] بعد إعادة تفعيل فلتر [الأحدث / Newest].")

                # Process this comment!
                stamp = time.strftime("%H:%M:%S")
                self.log("INFO", f"[{stamp}] 💬 معالجة تعليق جديد من [{author}]: \"{text_snippet[:50]}...\"")
                self.status = f"الرد على [{author}]..."

                success_public = False
                success_dm = False

                # Format message variables
                formatted_public = self._format_template(public_tpl, author, page_name)
                formatted_private = self._format_template(private_tpl, author, page_name)

                # A. Send Public Reply (Max 1 per user on this post)
                if action_type in ("reply_and_dm", "public_reply_only"):
                    if self._has_user_received_public(post_id, author, author_url, history):
                        self.log("INFO", f"تم إرسال رد عام مسبقاً لـ [{author}] على هذا المنشور. تخطي الرد العام.")
                        success_public = True
                    elif c.get("hasReplyButton"):
                        success_public = self._send_public_reply(c, formatted_public)
                        if success_public:
                            self.stats["replies_sent"] += 1
                            self._mark_user_action_on_post(post_id, author, author_url, history, "public", time.time())
                            self.log("SUCCESS", f"✓ [{stamp}] تم نشر الرد العام بنجاح على تعليق [{author}]")
                            self.sleep(random.uniform(2.5, 4.5))
                        else:
                            self.log("WARNING", f"تعذر إرسال الرد العام على تعليق [{author}]")
                    else:
                        self.log("INFO", f"زر الرد العام غير ظاهر لتعليق [{author}]")

                # B. Send Private Messenger DM (Max 1 per user on this post)
                if action_type in ("reply_and_dm", "dm_only") and not self.stop_requested:
                    if self._has_user_received_dm(post_id, author, author_url, history):
                        self.log("INFO", f"تم إرسال رسالة خاصة مسبقاً لـ [{author}] على هذا المنشور. تخطي الخاص.")
                        success_dm = True
                    elif c.get("hasDmButton"):
                        success_dm = self._send_private_dm(c, formatted_private)
                        if success_dm:
                            self.stats["dms_sent"] += 1
                            self._mark_user_action_on_post(post_id, author, author_url, history, "dm", time.time())
                            self.log("SUCCESS", f"✓ [{stamp}] تم إرسال رسالة مسنجر خاصة لـ [{author}]")
                            self.sleep(random.uniform(2.0, 3.5))
                        else:
                            self.log("INFO", f"لم تكتمل رسالة الخاص لـ [{author}] (قد تكون مقيدة بالصفحة)")
                    else:
                        if action_type == "dm_only":
                            self.log("INFO", f"زر إرسال الرسالة الخاصة غير متاح لـ [{author}]")

                # If either public reply or DM succeeded, mark comment as processed
                is_success = False
                if action_type == "reply_and_dm":
                    is_success = (success_public or success_dm)
                elif action_type == "public_reply_only":
                    is_success = success_public
                elif action_type == "dm_only":
                    is_success = success_dm

                if is_success:
                    now_stamp = time.time()
                    history[cid] = now_stamp
                    
                    # Mark user as done on this post to strictly prevent duplicate comments/DMs
                    if action_type == "reply_and_dm":
                        if success_public and success_dm:
                            self._mark_user_action_on_post(post_id, author, author_url, history, "done", now_stamp)
                        elif success_public and not c.get("hasDmButton"):
                            self._mark_user_action_on_post(post_id, author, author_url, history, "dm_unavail", now_stamp)
                            self._mark_user_action_on_post(post_id, author, author_url, history, "done", now_stamp)
                        elif success_dm and not c.get("hasReplyButton"):
                            self._mark_user_action_on_post(post_id, author, author_url, history, "done", now_stamp)
                        else:
                            self._mark_user_action_on_post(post_id, author, author_url, history, "done", now_stamp)
                    else:
                        self._mark_user_action_on_post(post_id, author, author_url, history, "done", now_stamp)

                    if cooldown_hours > 0:
                        user_keys = self._get_user_identifiers(author, author_url)
                        for uk in user_keys:
                            history[f"user_{uk}"] = now_stamp

                    self._save_history(history)
                    reply_timestamps.append(now_stamp)
                    action_taken_in_pass += 1

                    # Jittered human rest cooldown between comments
                    rest = random.uniform(10.0, 18.0)
                    self.status = f"تبريد أمان ({rest:.0f}ث)..."
                    self.sleep(rest)
                else:
                    self.log("INFO", f"لم يكتمل الرد على تعليق [{author}] في هذه الدورة. سيتم إعادة المحاولة تلقائياً.")

            if action_taken_in_pass > 0:
                consecutive_empty_cycles = 0
            else:
                consecutive_empty_cycles += 1
                self.status = f"انتظار ({int(check_interval)}ث)"
                self.log("INFO", f"لا توجد تعليقات جديدة غير معالجة. انتظار {int(check_interval)} ثانية...")
                self.sleep(check_interval)

                # Soft trigger: gentle scroll to ping Facebook socket for new comments
                self._gentle_scroll()

                # Only if completely stuck for 6 consecutive cycles (approx 4-5 minutes), soft re-check sorting
                if consecutive_empty_cycles % 6 == 0 and not self.stop_requested:
                    self._ensure_all_comments_sorted()

    def _format_template(self, template: str, author_name: str, page_name: str) -> str:
        """Injects {name} and {page} tags safely into template strings."""
        res = template or ""
        clean_name = re.sub(r"[@_]+", "", author_name).strip()
        res = res.replace("{name}", clean_name)
        res = res.replace("{username}", clean_name)
        res = res.replace("{page}", page_name)
        return res.strip()

    def _refresh_comments_filter_newest(self) -> bool:
        """
        Unconditionally opens the comment filter dropdown and selects 'Newest' (or 'All comments')
        to force Facebook to reload comments and mount the 'Reply' and 'Send message' buttons.
        """
        now = time.time()
        last_refresh = getattr(self, "_last_filter_refresh", 0.0)
        if now - last_refresh < 5.0:
            self.log("INFO", "⏳ تم تحديث فلتر التعليقات مؤخراً (أقل من 5 ثوانٍ)، تخطي إعادة النقر لتجنب التكرار.")
            return False

        try:
            self.log("INFO", "🔄 إعادة تفعيل فلتر التعليقات [الأحدث / Newest] لإظهار أزرار الرد والخاص...")
            open_res = self.driver.execute_script(OPEN_COMMENT_FILTER_DROPDOWN_JS)
            if not (isinstance(open_res, dict) and open_res.get("clicked")):
                self.log("INFO", "لم يتم العثور على زر فلتر ترتيب التعليقات في الصفحة.")
                return False

            # Wait and poll for the menu options to mount and be selected
            sel_res = None
            for _ in range(6):
                self.sleep(0.5)
                sel_res = self.driver.execute_script(SELECT_NEWEST_MENUITEM_JS)
                if isinstance(sel_res, dict) and sel_res.get("success"):
                    break

            if isinstance(sel_res, dict) and sel_res.get("success"):
                item_name = sel_res.get('text', 'Newest')
                self.log("SUCCESS", f"✅ تم اختيار [{item_name}] في فلتر التعليقات بنجاح.")
                self._last_filter_refresh = time.time()
                self.sleep(random.uniform(2.5, 3.5))
                return True
            else:
                self.log("INFO", "لم يتم العثور على خيار [الأحدث / Newest] في القائمة المفتوحة بعد فتحها.")
        except Exception as e:
            self.log("WARNING", f"خطأ أثناء تحديث فلتر التعليقات: {e}")
        return False

    def _ensure_all_comments_sorted(self) -> None:
        """Checks current comment sorting and switches to 'Newest' or 'All Comments' if needed."""
        try:
            res = self.driver.execute_script(SWITCH_COMMENT_SORTING_JS)
            if isinstance(res, dict) and res.get("needSwitch"):
                self.log("INFO", "🔄 جاري تحويل فلتر التعليقات إلى [الأحدث / Newest / All Comments]...")
                self.sleep(random.uniform(1.0, 1.8))
                sel_res = self.driver.execute_script(SELECT_NEWEST_MENUITEM_JS)
                if isinstance(sel_res, dict) and sel_res.get("success"):
                    self.log("SUCCESS", f"✅ تم تحويل الفلتر بنجاح إلى [{sel_res.get('text', 'Newest')}].")
                    self.sleep(random.uniform(2.5, 4.0))
        except Exception:
            pass

    def _expand_more_comments(self) -> None:
        """Clicks 'View more comments' buttons smoothly to paginate without full page reload."""
        try:
            res = self.driver.execute_script(CLICK_EXPAND_COMMENTS_JS)
            if isinstance(res, dict) and res.get("clicked", 0) > 0:
                self.sleep(random.uniform(1.5, 2.5))
        except Exception:
            pass

    def _extract_comments(self, page_name: str) -> List[Dict[str, Any]]:
        """Extracts structured comment rows via DOM JavaScript."""
        try:
            res = self.driver.execute_script(EXTRACT_COMMENTS_JS, page_name)
            if isinstance(res, list):
                return res
        except Exception as e:
            self.log("WARNING", f"خطأ أثناء استخراج التعليقات: {e}")
        return []

    def _send_public_reply(self, comment_item: Dict[str, Any], reply_text: str) -> bool:
        """Finds the reply button for the specific comment, types the reply, and submits it."""
        idx = comment_item.get("index", 0)
        author = comment_item.get("author", "")
        comment_id = comment_item.get("commentId", "")

        # 1. Click Reply button on that specific comment
        clicked = False
        try:
            clicked = bool(self.driver.execute_script("""
                const commentId = arguments[0];
                const author = arguments[1];
                const artIdx = arguments[2];
                const articles = Array.from(document.querySelectorAll('div[role="article"]'));
                let art = null;
                if (commentId) {
                    art = articles.find(a => {
                        const lks = Array.from(a.querySelectorAll('a[href*="comment_id="]'));
                        return lks.some(l => (l.getAttribute('href') || '').includes(commentId));
                    });
                }
                if (!art && author) {
                    art = articles.find(a => (a.getAttribute('aria-label') || '').toLowerCase().includes(author.toLowerCase()));
                }
                if (!art && artIdx < articles.length) art = articles[artIdx];
                if (!art) return false;

                function findReply(node) {
                    const btns = Array.from(node.querySelectorAll('[role="button"], button'));
                    return btns.find(b => {
                        const t = (b.innerText || '').toLowerCase().trim();
                        const a = (b.getAttribute('aria-label') || '').toLowerCase().trim();
                        return t === 'reply' || t === 'رد' || a === 'reply' || a === 'رد' ||
                               t.startsWith('reply') || t.startsWith('رد ');
                    });
                }

                let replyBtn = findReply(art);
                if (!replyBtn) {
                    art.scrollIntoView({ block: 'center', behavior: 'instant' });
                    art.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    art.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                    replyBtn = findReply(art);
                }

                if (replyBtn) {
                    replyBtn.scrollIntoView({ block: 'center', behavior: 'instant' });
                    replyBtn.click();
                    return true;
                }
                return false;
            """, comment_id, author, idx))
        except Exception:
            pass

        if not clicked:
            return False

        self.sleep(random.uniform(1.5, 2.5))

        # 2. Find the reply textbox opened under or associated with this comment
        textbox = None
        try:
            textbox = self.driver.execute_script("""
                const commentId = arguments[0];
                const author = arguments[1];
                const artIdx = arguments[2];
                const articles = Array.from(document.querySelectorAll('div[role="article"]'));
                let art = null;
                if (commentId) {
                    art = articles.find(a => {
                        const lks = Array.from(a.querySelectorAll('a[href*="comment_id="]'));
                        return lks.some(l => (l.getAttribute('href') || '').includes(commentId));
                    });
                }
                if (!art && author) {
                    art = articles.find(a => (a.getAttribute('aria-label') || '').toLowerCase().includes(author.toLowerCase()));
                }
                if (!art && artIdx < articles.length) art = articles[artIdx];

                let tb = null;
                // 1. Look inside thread container
                if (art) {
                    const thread = art.closest('.x18xomjl') || art.closest('.xbcz3fp') || art.parentElement.closest('div.html-div') || art.parentElement;
                    if (thread) {
                        tb = thread.querySelector('div[role="textbox"][contenteditable="true"]');
                    }
                }
                // 2. Look for textbox with author in aria-label or aria-placeholder
                if (!tb && author) {
                    const lowerAuth = author.toLowerCase();
                    const boxes = Array.from(document.querySelectorAll('div[role="textbox"][contenteditable="true"]'));
                    tb = boxes.find(b => {
                        const a = (b.getAttribute('aria-label') || '').toLowerCase();
                        const p = (b.getAttribute('aria-placeholder') || '').toLowerCase();
                        return (a.includes(lowerAuth) || p.includes(lowerAuth)) && (a.includes('reply') || a.includes('رد') || p.includes('reply') || p.includes('رد'));
                    });
                }
                // 3. Fallback to active focused element if it is a textbox
                if (!tb && document.activeElement && document.activeElement.getAttribute('contenteditable') === 'true') {
                    tb = document.activeElement;
                }
                // 4. Global reply box
                if (!tb) {
                    const boxes = Array.from(document.querySelectorAll('div[role="textbox"][contenteditable="true"]'));
                    tb = boxes.find(b => {
                        const a = (b.getAttribute('aria-label') || '').toLowerCase();
                        return a.includes('reply') || a.includes('رد') || a.includes('اكتب رداً') || a.includes('write a reply');
                    });
                }

                if (tb) {
                    tb.scrollIntoView({ block: 'center', behavior: 'instant' });
                    tb.focus();
                    return tb;
                }
                return null;
            """, comment_id, author, idx)
        except Exception:
            pass

        if not textbox:
            # Fallback via Selenium Find Elements
            try:
                boxes = self.driver.find_elements(By.XPATH, '//div[@role="textbox" and @contenteditable="true"]')
                for b in boxes:
                    if b.is_displayed():
                        textbox = b
                        break
            except Exception:
                pass

        if not textbox:
            return False

        # 3. Type reply with human cadence
        try:
            self.type_letter_by_letter(textbox, reply_text)
            self.sleep(random.uniform(0.8, 1.4))

            # Dispatch synthetic input/change events for React
            self.driver.execute_script("""
                const el = arguments[0];
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            """, textbox)
            self.sleep(0.4)

            # Submit via Enter key
            textbox.send_keys(Keys.ENTER)
            self.sleep(0.5)
            self.driver.execute_script("""
                const el = arguments[0];
                el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
            """, textbox)
            self.sleep(random.uniform(2.0, 3.0))
            return True
        except Exception as e:
            if "stale" in str(e).lower():
                try:
                    active = self.driver.execute_script("return document.activeElement || document.querySelector('div[role=\"textbox\"][contenteditable=\"true\"]');")
                    if active:
                        active.send_keys(Keys.ENTER)
                        self.sleep(random.uniform(2.0, 3.0))
                        return True
                except Exception:
                    pass
            self.log("WARNING", f"خطأ أثناء كتابة أو إرسال الرد العام: {e}")
            return False

    def _send_private_dm(self, comment_item: Dict[str, Any], dm_text: str) -> bool:
        """Clicks 'Send message' on the comment, types in Messenger modal dialog, clicks 'Send message' button, and verifies submission."""
        idx = comment_item.get("index", 0)
        author = comment_item.get("author", "")
        comment_id = comment_item.get("commentId", "")

        # 1. Click "Send message" / "إرسال رسالة" on this comment
        clicked = False
        try:
            clicked = bool(self.driver.execute_script("""
                const commentId = arguments[0];
                const author = arguments[1];
                const artIdx = arguments[2];
                const articles = Array.from(document.querySelectorAll('div[role="article"]'));
                let art = null;
                if (commentId) {
                    art = articles.find(a => {
                        const lks = Array.from(a.querySelectorAll('a[href*="comment_id="]'));
                        return lks.some(l => (l.getAttribute('href') || '').includes(commentId));
                    });
                }
                if (!art && author) {
                    art = articles.find(a => (a.getAttribute('aria-label') || '').toLowerCase().includes(author.toLowerCase()));
                }
                if (!art && artIdx < articles.length) art = articles[artIdx];
                if (!art) return false;

                function findDm(node) {
                    const btns = Array.from(node.querySelectorAll('[role="button"], button'));
                    return btns.find(b => {
                        const t = (b.innerText || '').toLowerCase().trim();
                        const a = (b.getAttribute('aria-label') || '').toLowerCase().trim();
                        return t.includes('send message') || t.includes('إرسال رسالة') ||
                               t.includes('message') || t.includes('مراسلة') ||
                               a.includes('send message') || a.includes('إرسال رسالة');
                    });
                }

                let dmBtn = findDm(art);
                if (!dmBtn) {
                    art.scrollIntoView({ block: 'center', behavior: 'instant' });
                    art.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    art.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                    dmBtn = findDm(art);
                }

                if (dmBtn) {
                    dmBtn.scrollIntoView({ block: 'center', behavior: 'instant' });
                    dmBtn.click();
                    return true;
                }
                return false;
            """, comment_id, author, idx))
        except Exception:
            pass

        if not clicked:
            return False

        self.sleep(random.uniform(2.0, 3.0))

        # 2. Find the modal dialog or Messenger chat box
        dm_box = None
        dialog_el = None
        for _ in range(6):
            try:
                dialogs = self.driver.find_elements(By.XPATH, '//div[@role="dialog" and @aria-modal="true"] | //div[@role="dialog"]')
                for d in dialogs:
                    if d.is_displayed():
                        dialog_el = d
                        boxes = d.find_elements(By.XPATH, './/div[@role="textbox" and @contenteditable="true"] | .//div[@data-lexical-editor="true"]')
                        for b in boxes:
                            if b.is_displayed():
                                dm_box = b
                                break
                        if dm_box:
                            break
            except Exception:
                pass
            if dm_box:
                break
            self.sleep(0.4)

        if not dm_box:
            # Fallback to any visible textbox with Send message placeholder
            try:
                boxes = self.driver.find_elements(By.XPATH, '//div[@role="textbox" and @contenteditable="true"]')
                for b in boxes:
                    if b.is_displayed():
                        dm_box = b
                        break
            except Exception:
                pass

        if not dm_box:
            self._close_messenger_dock()
            return False

        # 3. Type the message
        sent = False
        try:
            try:
                dm_box.click()
            except Exception:
                pass
            self.sleep(0.3)

            self.type_letter_by_letter(dm_box, dm_text)
            self.sleep(random.uniform(0.6, 1.2))

            # Dispatch rich input events so Lexical editor registers input
            self.driver.execute_script("""
                const el = arguments[0];
                const text = arguments[1];
                el.focus();
                try {
                    el.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, cancelable: true, inputType: 'insertText', data: text }));
                    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                } catch(e) {}
            """, dm_box, dm_text)
            self.sleep(0.3)

            # Flush React state with a space + backspace
            try:
                dm_box.send_keys(" ")
                self.sleep(0.1)
                dm_box.send_keys(Keys.BACKSPACE)
                self.sleep(0.5)
            except Exception:
                pass

            # 4. CRITICAL: Click the "Send message" button inside the modal dialog!
            click_res = self.driver.execute_script(FIND_AND_CLICK_DM_SEND_BUTTON_JS)
            if isinstance(click_res, dict) and click_res.get("clicked"):
                self.log("INFO", f"تم النقر على زر [{click_res.get('label', 'Send message')}]")
            else:
                # Also try finding via Selenium By.XPATH
                try:
                    send_buttons = self.driver.find_elements(By.XPATH, """
                        //div[@role="dialog"]//div[@role="button" and (@aria-label="Send message" or @aria-label="إرسال رسالة" or contains(@aria-label, "Send") or contains(@aria-label, "إرسال"))] |
                        //div[@role="dialog"]//div[@role="button"][.//span[contains(text(), "Send message") or contains(text(), "إرسال")]]
                    """)
                    for sb in send_buttons:
                        if sb.is_displayed() and not any(x in (sb.get_attribute("aria-label") or "").lower() for x in ["close", "إغلاق", "back", "رجوع"]):
                            sb.click()
                            break
                except Exception:
                    pass

                # Also try sending Enter as fallback for Messenger chat dock
                try:
                    dm_box.send_keys(Keys.ENTER)
                except Exception:
                    pass

            # 5. Wait for message to be submitted and dialog to close
            for _ in range(7):
                self.sleep(0.5)
                still_open = self.driver.execute_script("""
                    const d = document.querySelector('div[role="dialog"]');
                    if (!d || d.offsetHeight === 0) return false;
                    const tb = d.querySelector('div[role="textbox"]');
                    if (!tb || (tb.innerText || '').trim() === '') return false;
                    return true;
                """)
                if not still_open:
                    sent = True
                    break

            if not sent:
                # Try clicking send once more
                self.driver.execute_script(FIND_AND_CLICK_DM_SEND_BUTTON_JS)
                self.sleep(1.5)
                sent = True

        except Exception as e:
            self.log("WARNING", f"خطأ أثناء إرسال رسالة ماسنجر: {e}")

        # 6. Safely dismiss the dialog if still open after sending, and close any dock
        try:
            self.driver.execute_script("""
                const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
                for (const d of dialogs) {
                    const closeBtn = d.querySelector('div[aria-label="Close"], div[aria-label="إغلاق"], div[aria-label="Go back to comment"], div[aria-label="الرجوع للتعليق"]');
                    if (closeBtn && (closeBtn.offsetParent || closeBtn.offsetHeight > 0)) {
                        closeBtn.click();
                        break;
                    }
                }
            """)
            self.sleep(0.5)
        except Exception:
            pass

        self._close_messenger_dock()
        return sent

    def _close_messenger_dock(self) -> None:
        """Safely closes any open Messenger chat docks or dialogs to keep the view unobstructed."""
        try:
            self.driver.execute_script(CLOSE_MESSENGER_DOCK_JS)
            self.sleep(0.5)
        except Exception:
            pass

    def _check_facebook_restrictions(self) -> Tuple[bool, str]:
        """Checks for Facebook action block or temporary restriction dialogs."""
        try:
            res = self.driver.execute_script(CHECK_FB_RESTRICTIONS_JS)
            if isinstance(res, dict) and res.get("detected"):
                return True, str(res.get("message") or "تم اكتشاف تنبيه تقييد من فيسبوك")
        except Exception:
            pass
        return False, ""

    def _gentle_scroll(self) -> None:
        """Gently scrolls up and down the active comments container to keep Facebook socket live."""
        try:
            self.driver.execute_script("""
                const ref = document.querySelector('div[role="article"]') ||
                            document.querySelector('div[data-ad-rendering-role="story_message"]') ||
                            document.querySelector('form');
                let scroller = null;
                if (ref) {
                    let el = ref.parentElement;
                    while (el && el !== document.body && el !== document.documentElement) {
                        const cs = window.getComputedStyle(el);
                        if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 20) {
                            scroller = el;
                            break;
                        }
                        el = el.parentElement;
                    }
                }
                if (!scroller) {
                    const candidates = Array.from(document.querySelectorAll('div.xq1qtft, div.xb57i2i, div[role="dialog"]'));
                    for (const c of candidates) {
                        const cs = window.getComputedStyle(c);
                        if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && c.scrollHeight > c.clientHeight + 20) {
                            scroller = c;
                            break;
                        }
                    }
                }
                if (!scroller) {
                    scroller = document.scrollingElement || document.documentElement || document.body;
                }

                if (scroller && scroller !== document.body && scroller !== document.documentElement) {
                    scroller.scrollBy({ top: 350, behavior: 'smooth' });
                    setTimeout(() => scroller.scrollBy({ top: -350, behavior: 'smooth' }), 600);
                } else {
                    window.scrollBy({ top: 350, behavior: 'smooth' });
                    setTimeout(() => window.scrollBy({ top: -350, behavior: 'smooth' }), 600);
                }
            """)
            self.sleep(1.2)
        except Exception:
            pass

    def _scroll_paginate_comments(self) -> None:
        """Performs progressive scrolling inside the nested comments container to load virtualized comments."""
        try:
            self.driver.execute_script("""
                const ref = document.querySelector('div[role="article"]') ||
                            document.querySelector('div[data-ad-rendering-role="story_message"]') ||
                            document.querySelector('form');
                let scroller = null;
                if (ref) {
                    let el = ref.parentElement;
                    while (el && el !== document.body && el !== document.documentElement) {
                        const cs = window.getComputedStyle(el);
                        if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 20) {
                            scroller = el;
                            break;
                        }
                        el = el.parentElement;
                    }
                }
                if (!scroller) {
                    const candidates = Array.from(document.querySelectorAll('div.xq1qtft, div.xb57i2i, div[role="dialog"]'));
                    for (const c of candidates) {
                        const cs = window.getComputedStyle(c);
                        if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && c.scrollHeight > c.clientHeight + 20) {
                            scroller = c;
                            break;
                        }
                    }
                }
                if (scroller && scroller !== document.body && scroller !== document.documentElement) {
                    scroller.scrollBy({ top: 600, behavior: 'smooth' });
                } else {
                    window.scrollBy({ top: 600, behavior: 'smooth' });
                }
            """)
            self.sleep(1.5)
        except Exception:
            pass
