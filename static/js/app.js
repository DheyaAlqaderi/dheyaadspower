// AdsPower Multi-Platform Automation Hub - Client Logic (v3.0 ULTRA)

let state = {
    activeTab: 'overview',
    selectedPlatform: 'facebook',
    bulkAutomationMode: 'saved',
    profiles: [],
    selectedProfileIds: new Set(),
    selectedAutomationProfileIds: new Set(),
    autoProfileSearchQuery: '',
    autoProfileFilterMode: 'all', // 'all', 'active', 'ready'
    proxies: [],
    config: {},
    isAutomationRunning: false,
    lastLogId: 0,
    totalLogLines: 0,
    allLogs: []
};

// Platform Specific Defaults & Quick Preset Templates Library
const PLATFORM_CONFIGS = {
    facebook: {
        title: "إعدادات أتمتة فيسبوك (Facebook)",
        urlLabel: "رابط منشور فيسبوك (Post URL)",
        urlPlaceholder: "https://www.facebook.com/...",
        urlHint: "رابط منشور فيسبوك المستهدف",
        publicLabel: "قالب الرد العام (Public Reply)",
        publicDefault: "Hello {name}! Thanks for reaching out. Please check your inbox 📩",
        dmLabel: "قالب رسالة الخاص (Private DM)",
        dmDefault: "Hi {name}, thank you for your comment! How can we assist you with our store today?",
        hasPublic: true,
        hasDm: true,
        hasPageName: true,
        hasTwPresets: false,
        hasTwCooldown: false,
        delayDefault: 35,
        presets: {
            public: [
                { label: "استفسار وتفاصيل 📩", text: "أهلاً بك {name}! شكراً لاهتمامك، تم الرد على الخاص بكافة التفاصيل 📩" },
                { label: "تحويل للواتساب 📲", text: "مرحباً {name}! للطلب والاستفسار الفوري تواصل معنا عبر واتساب 📲" },
                { label: "شكر وتقدير 💬", text: "شكراً لمرورك العطر {name}! نسعد بخدمتك دائماً 💬✨" }
            ],
            dm: [
                { label: "عرض وأسعار 🎁", text: "مرحباً {name}، يسعدنا تواصلك معنا! أرسلنا لك تفاصيل العرض والأسعار، كيف يمكننا مساعدتك اليوم؟" },
                { label: "خدمة عملاء 🛍️", text: "أهلاً {name}! بخصوص استفسارك على المنشور، نحن هنا للإجابة على جميع تساؤلاتك ومساعدتك في إتمام طلبك." }
            ]
        }
    },
    instagram: {
        title: "إعدادات أتمتة ريلز ومنشورات إنستغرام (Reels & Posts Reply + DM)",
        urlLabel: "روابط ريلز أو منشورات إنستغرام (يمكن وضع رابط أو عدة روابط، كل رابط في سطر)",
        urlPlaceholder: "https://www.instagram.com/p/C4M8PnrMbHu/\nhttps://www.instagram.com/p/C5cpZiaoHQx/",
        urlHint: "يدعم عدة روابط (رابط بكل سطر)",
        publicLabel: "قالب الرد العام على التعليق (Public Reply)",
        publicDefault: "Appreciate your thoughts on this! Check your DMs 💬",
        dmLabel: "قالب رسالة الخاص (Private DM)",
        dmDefault: "Hey! Reached out regarding your comment on the post. Hope you're having a great day! 😊",
        hasPublic: true,
        hasDm: true,
        hasPageName: false,
        hasTwPresets: false,
        hasTwCooldown: false,
        delayDefault: 35,
        presets: {
            public: [
                { label: "رد + تفاصيل بالخاص 📩", text: "أهلاً بك {name}! تم إرسال كافة التفاصيل في رسالة خاصة 📩" },
                { label: "رابط البايو 🔗", text: "مرحباً {name}! يمكنك الاطلاع على كافة المنتجات عبر الرابط في البايو 🔗" },
                { label: "كود خصم حصري 🎁", text: "شكراً لتفاعلك {name}! استخدم كود الخصم الحصري المرسل لك في الخاص ✨" }
            ],
            dm: [
                { label: "تفاصيل الريلز 🌟", text: "أهلاً {name}! شكراً لتعليقك على الريلز، تفاصيل المنتج والطلب موضحة هنا. هل ترغب في إتمام الطلب؟" },
                { label: "ترحيب بالمتجر 🛍️", text: "مرحباً بك {name} في متجرنا! يسعدنا تقديم المساعدة بخصوص أي استفسار لديك." }
            ]
        }
    },
    twitter: {
        title: "إعدادات أتمتة الرد التلقائي على رسائل X الخاصة (X / Twitter DM Auto-Reply)",
        urlLabel: "رابط صندوق المحادثات أو طلبات المراسلة (DM Inbox / Requests URL)",
        urlPlaceholder: "https://x.com/i/chat",
        urlHint: "/i/chat أو requests/other",
        publicLabel: "",
        publicDefault: "",
        dmLabel: "قالب رسالة الرد التلقائي على الخاص (Auto Reply DM Message)",
        dmDefault: "مرحباً بك! شكراً لتواصلك معنا، نسعد بخدمتك دائماً 💬✨",
        hasPublic: false,
        hasDm: true,
        hasPageName: false,
        hasTwPresets: true,
        hasTwCooldown: true,
        delayDefault: 12,
        presets: {
            dm: [
                { label: "ترحيب عام 💬", text: "مرحباً بك! شكراً لتواصلك معنا، نسعد بخدمتك دائماً 💬✨" },
                { label: "دعم فني سريع 🛠️", text: "أهلاً بك! تلقينا رسالتك وسيقوم فريق الدعم بمساعدتك فوراً. يرجى تزويدنا بالتفاصيل." },
                { label: "استفسار خدمات 🚀", text: "مرحباً! شكراً لاهتمامك بخدماتنا، كيف يمكننا مساعدتك اليوم؟" }
            ]
        }
    },
    tiktok: {
        title: "إعدادات أتمتة تيك توك (TikTok)",
        urlLabel: "رابط الفيديو أو الحساب المستهدف (Video / Profile URL)",
        urlPlaceholder: "https://www.tiktok.com/@...",
        urlHint: "رابط الفيديو أو الحساب",
        publicLabel: "قالب التعليق على الفيديوهات",
        publicDefault: "Amazing content! Loved this video 🔥",
        dmLabel: "",
        dmDefault: "",
        hasPublic: true,
        hasDm: false,
        hasPageName: false,
        hasTwPresets: false,
        hasTwCooldown: false,
        delayDefault: 20,
        presets: {
            public: [
                { label: "شكراً لتفاعلك 🎵", text: "شكراً لمرورك الجميل {name}! تابع الحساب للمزيد من العروض 🎵✨" },
                { label: "رابط البايو 🔗", text: "أهلاً {name}! تفاصيل الطلب كاملة متوفرة في رابط البايو 🔗" }
            ]
        }
    }
};

// ======================== INITIALIZATION ========================
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    checkSystemStatus();
    loadProfiles();
    loadProxies();
    selectPlatform('facebook');

    // Auto status poller
    setInterval(() => {
        checkSystemStatus(false);
    }, 3000);

    // Runner logs & stats poller
    setInterval(() => {
        pollRunner();
    }, 1500);
});

// ======================== TAB SWITCHING ========================
function switchTab(tabId) {
    state.activeTab = tabId;

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active-tab');
        btn.classList.add('text-slate-400');
    });

    const activeBtn = document.getElementById(`tab-btn-${tabId}`);
    if (activeBtn) {
        activeBtn.classList.add('active-tab');
        activeBtn.classList.remove('text-slate-400');
    }

    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.add('hidden');
    });

    const activeContent = document.getElementById(`tab-content-${tabId}`);
    if (activeContent) {
        activeContent.classList.remove('hidden');
    }

    if (tabId === 'profiles') loadProfiles();
    if (tabId === 'proxies') loadProxies();
}

function openPlatformAutomation(platform) {
    switchTab('automation');
    selectPlatform(platform);
}

// ======================== PLATFORM & EXECUTION MODE SWITCHER ========================
function setBulkAutomationMode(mode) {
    state.bulkAutomationMode = mode;
    const btnSaved = document.getElementById('auto-mode-btn-saved');
    const btnCustom = document.getElementById('auto-mode-btn-custom');
    const notice = document.getElementById('auto-saved-mode-notice');
    const customContainer = document.getElementById('auto-custom-inputs-container');
    const badge = document.getElementById('auto-mode-indicator-badge');

    if (mode === 'saved') {
        if (btnSaved) {
            btnSaved.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center gap-1.5 shadow-sm";
        }
        if (btnCustom) {
            btnCustom.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all bg-slate-800 text-slate-400 hover:text-white border border-slate-700/50 flex items-center gap-1.5";
        }
        if (notice) notice.classList.remove('hidden');
        if (customContainer) {
            customContainer.classList.add('opacity-60', 'pointer-events-none');
        }
        if (badge) {
            badge.textContent = "إعدادات كل ملف محفوظة";
            badge.className = "text-[10px] font-bold px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
        }
        showToast("تم تفعيل نمط استخدام الإعدادات والروابط المحفوظة لكل ملف", "info");
    } else {
        if (btnSaved) {
            btnSaved.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all bg-slate-800 text-slate-400 hover:text-white border border-slate-700/50 flex items-center gap-1.5";
        }
        if (btnCustom) {
            btnCustom.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all bg-indigo-500/20 text-indigo-400 border border-indigo-500/40 flex items-center gap-1.5 shadow-sm";
        }
        if (notice) notice.classList.add('hidden');
        if (customContainer) {
            customContainer.classList.remove('opacity-60', 'pointer-events-none');
        }
        if (badge) {
            badge.textContent = "إعدادات موحدة مخصصة";
            badge.className = "text-[10px] font-bold px-2 py-0.5 rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20";
        }
        showToast("تم تفعيل نمط تخصيص إعدادات وروابط موحدة للجميع", "info");
    }
}

function setBulkTwUrl(url) {
    const urlInput = document.getElementById('auto-post-url');
    if (urlInput) {
        urlInput.value = url;
        showToast(`تم تعيين الرابط: ${url}`, "info");
    }
}

function setBulkTwCooldown(hours) {
    const cooldownInput = document.getElementById('auto-tw-cooldown');
    if (cooldownInput) {
        cooldownInput.value = hours;
        cooldownInput.dispatchEvent(new Event('input'));
        if (hours === 0 || hours === '0') {
            showToast("تم تعطيل فترة الانتظار (Cooldown: 0) - الرد على جميع الرسائل الواردة فوراً ⚡", "info");
        } else {
            showToast(`تم تحديد فترة التبريد: ${hours} ساعة`, "info");
        }
    }
}

function renderTemplatePresetChips() {
    const plat = state.selectedPlatform || 'facebook';
    const cfg = PLATFORM_CONFIGS[plat] || {};
    const presets = cfg.presets || { public: [], dm: [] };

    const pubContainer = document.getElementById('public-template-chips');
    if (pubContainer) {
        if (presets.public && presets.public.length > 0) {
            pubContainer.innerHTML = presets.public.map((item, idx) => `
                <button type="button" onclick="insertTemplatePreset('public', ${idx})" class="text-[10px] px-2 py-0.5 rounded-lg bg-emerald-950/40 hover:bg-emerald-900/60 text-emerald-300 border border-emerald-800/40 transition-all flex items-center gap-1 shadow-sm cursor-pointer" title="اضغط لملء القالب">
                    <i class="fa-solid fa-sparkles text-[9px] text-amber-300"></i>
                    <span>${escapeHtml(item.label)}</span>
                </button>
            `).join('');
            pubContainer.classList.remove('hidden');
        } else {
            pubContainer.innerHTML = '';
            pubContainer.classList.add('hidden');
        }
    }

    const dmContainer = document.getElementById('dm-template-chips');
    if (dmContainer) {
        if (presets.dm && presets.dm.length > 0) {
            dmContainer.innerHTML = presets.dm.map((item, idx) => `
                <button type="button" onclick="insertTemplatePreset('dm', ${idx})" class="text-[10px] px-2 py-0.5 rounded-lg bg-purple-950/40 hover:bg-purple-900/60 text-purple-300 border border-purple-800/40 transition-all flex items-center gap-1 shadow-sm cursor-pointer" title="اضغط لملء القالب">
                    <i class="fa-solid fa-wand-magic-sparkles text-[9px] text-purple-400"></i>
                    <span>${escapeHtml(item.label)}</span>
                </button>
            `).join('');
            dmContainer.classList.remove('hidden');
        } else {
            dmContainer.innerHTML = '';
            dmContainer.classList.add('hidden');
        }
    }
}

function insertTemplatePreset(type, index) {
    const plat = state.selectedPlatform || 'facebook';
    const cfg = PLATFORM_CONFIGS[plat] || {};
    const presets = cfg.presets || {};
    const item = (presets[type] || [])[index];
    if (!item) return;

    if (type === 'public') {
        const input = document.getElementById('auto-public-template');
        if (input) {
            input.value = item.text;
            input.focus();
        }
    } else {
        const input = document.getElementById('auto-private-template');
        if (input) {
            input.value = item.text;
            input.focus();
        }
    }
    showToast(`تم تطبيق قالب [${item.label}] بنجاح!`, "info");
}

function insertVariableTag(tag, targetTextareaId) {
    const el = document.getElementById(targetTextareaId);
    if (!el) return;
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    const text = el.value;
    el.value = text.substring(0, start) + tag + text.substring(end);
    el.focus();
    el.selectionStart = el.selectionEnd = start + tag.length;
}

function selectPlatform(platform) {
    state.selectedPlatform = platform;

    document.querySelectorAll('.platform-tab').forEach(btn => {
        btn.classList.remove('active-platform-tab');
        btn.classList.add('border-slate-800', 'text-slate-400');
    });

    const btn = document.getElementById(`platform-btn-${platform}`);
    if (btn) {
        btn.classList.add('active-platform-tab');
        btn.classList.remove('border-slate-800', 'text-slate-400');
    }

    const cfg = PLATFORM_CONFIGS[platform] || PLATFORM_CONFIGS.facebook;

    const titleEl = document.getElementById('automation-form-title');
    const urlLabel = document.getElementById('label-target-url');
    const urlInput = document.getElementById('auto-post-url');
    const urlHint = document.getElementById('target-url-hint');
    const publicContainer = document.getElementById('field-public-template-container');
    const publicLabel = document.getElementById('label-public-template');
    const publicTpl = document.getElementById('auto-public-template');
    const dmContainer = document.getElementById('field-dm-template-container');
    const dmLabel = document.getElementById('label-dm-template');
    const dmTpl = document.getElementById('auto-private-template');
    const pageContainer = document.getElementById('field-page-name-container');
    const intervalInput = document.getElementById('auto-check-interval');
    const twPresets = document.getElementById('field-tw-url-presets');
    const twCooldown = document.getElementById('field-tw-cooldown-container');

    if (titleEl) titleEl.textContent = cfg.title;
    if (urlLabel) urlLabel.textContent = cfg.urlLabel;
    if (urlHint) urlHint.textContent = cfg.urlHint || '';
    if (urlInput) {
        urlInput.placeholder = cfg.urlPlaceholder;
        if (platform === 'twitter' && !urlInput.value) {
            urlInput.value = 'https://x.com/i/chat';
        }
    }
    if (intervalInput) intervalInput.value = cfg.delayDefault;

    // Public Reply Container
    if (cfg.hasPublic) {
        if (publicContainer) publicContainer.classList.remove('hidden');
        if (publicLabel) publicLabel.textContent = cfg.publicLabel;
        if (publicTpl && (!publicTpl.value || publicTpl.dataset.platDefault !== platform)) {
            publicTpl.value = cfg.publicDefault;
            publicTpl.dataset.platDefault = platform;
        }
    } else {
        if (publicContainer) publicContainer.classList.add('hidden');
    }

    // DM Container
    if (cfg.hasDm) {
        if (dmContainer) dmContainer.classList.remove('hidden');
        if (dmLabel) dmLabel.textContent = cfg.dmLabel;
        if (dmTpl && (!dmTpl.value || dmTpl.dataset.platDefault !== platform)) {
            dmTpl.value = cfg.dmDefault;
            dmTpl.dataset.platDefault = platform;
        }
    } else {
        if (dmContainer) dmContainer.classList.add('hidden');
    }

    // Page Name Container (Facebook only)
    if (pageContainer) {
        if (cfg.hasPageName) {
            pageContainer.classList.remove('hidden');
        } else {
            pageContainer.classList.add('hidden');
        }
    }

    // Twitter-specific presets & cooldown
    if (twPresets) {
        if (cfg.hasTwPresets) {
            twPresets.classList.remove('hidden');
        } else {
            twPresets.classList.add('hidden');
        }
    }
    if (twCooldown) {
        if (cfg.hasTwCooldown) {
            twCooldown.classList.remove('hidden');
        } else {
            twCooldown.classList.add('hidden');
        }
    }

    renderTemplatePresetChips();
    renderAutomationProfileCheckboxes();
    updateStartAutomationButtonText();
}

// ======================== SYSTEM STATUS ========================
async function checkSystemStatus(manual = false) {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();

        const dot = document.getElementById('adspower-status-dot');
        const text = document.getElementById('adspower-status-text');

        if (data.adspower && data.adspower.connected) {
            dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50";
            text.textContent = "AdsPower متصل";
            text.className = "text-emerald-400 font-bold";
        } else {
            dot.className = "w-2.5 h-2.5 rounded-full bg-rose-500";
            text.textContent = "AdsPower غير متصل";
            text.className = "text-rose-400 font-bold";
        }

        const runnerBadge = document.getElementById('runner-badge');
        const runnerBadgeText = document.getElementById('runner-badge-text');
        const runningCount = data.runner ? (data.runner.running_count || 0) : 0;

        if (runningCount > 0) {
            runnerBadge.classList.remove('hidden');
            if (runnerBadgeText) runnerBadgeText.textContent = `الأتمتة نشطة (${runningCount} ملفات)`;
            state.isAutomationRunning = true;
        } else {
            runnerBadge.classList.add('hidden');
            state.isAutomationRunning = false;
        }

        const navProxyCount = document.getElementById('nav-proxy-count');
        const statOverviewProxies = document.getElementById('stat-overview-proxies');
        if (navProxyCount) navProxyCount.textContent = data.proxy_count || 0;
        if (statOverviewProxies) statOverviewProxies.textContent = data.proxy_count || 0;

        if (data.plan) {
            renderAdsPowerPlan(data.plan);
        }

        if (manual) {
            showToast(data.adspower.connected ? "AdsPower متصل بنجاح 🟢" : "تعذر الاتصال بـ AdsPower 🔴", data.adspower.connected ? "success" : "warning");
        }
    } catch (err) {
        console.error("Status error:", err);
    }
}

// ======================== ADSPOWER PLAN & EXPIRATION ========================
let currentPlanData = null;
let liveCountdownTimer = null;

function startLiveCountdown(expireTimestampSec) {
    if (liveCountdownTimer) {
        clearInterval(liveCountdownTimer);
        liveCountdownTimer = null;
    }
    if (!expireTimestampSec) return;

    function updateTick() {
        const nowSec = Date.now() / 1000;
        const diff = Math.floor(expireTimestampSec - nowSec);

        const days = Math.max(0, Math.floor(diff / 86400));
        const hours = Math.max(0, Math.floor((diff % 86400) / 3600));
        const mins = Math.max(0, Math.floor((diff % 3600) / 60));
        const secs = Math.max(0, diff % 60);

        const pad = (n) => String(n).padStart(2, '0');

        // Overview Card Counter Elements
        const cDays = document.getElementById('counter-days');
        const cHours = document.getElementById('counter-hours');
        const cMins = document.getElementById('counter-mins');
        const cSecs = document.getElementById('counter-secs');

        if (cDays) cDays.textContent = pad(days);
        if (cHours) cHours.textContent = pad(hours);
        if (cMins) cMins.textContent = pad(mins);
        if (cSecs) cSecs.textContent = pad(secs);

        // Modal Counter Elements
        const mDays = document.getElementById('modal-counter-days');
        const mHours = document.getElementById('modal-counter-hours');
        const mMins = document.getElementById('modal-counter-mins');
        const mSecs = document.getElementById('modal-counter-secs');

        if (mDays) mDays.textContent = pad(days);
        if (mHours) mHours.textContent = pad(hours);
        if (mMins) mMins.textContent = pad(mins);
        if (mSecs) mSecs.textContent = pad(secs);

        // Header Pill Text
        const planText = document.getElementById('adspower-plan-text');
        if (planText) {
            if (diff <= 0) {
                planText.textContent = "الاشتراك: منتهي الصلاحية";
                planText.className = "text-rose-400 font-bold";
            } else {
                planText.textContent = `الاشتراك: ${days}d ${pad(hours)}h ${pad(mins)}m ${pad(secs)}s`;
                planText.className = "text-amber-300 font-mono font-semibold";
            }
        }

        // Overview Countdown Live Tag
        const countdownLabel = document.getElementById('overview-plan-countdown-label');
        if (countdownLabel) {
            if (diff <= 0) {
                countdownLabel.textContent = "منتهي (EXPIRED)";
                countdownLabel.className = "text-[10px] text-rose-400 font-mono font-bold";
            } else {
                countdownLabel.textContent = `LIVE: -${pad(days)}:${pad(hours)}:${pad(mins)}:${pad(secs)}`;
            }
        }

        if (diff <= 0 && liveCountdownTimer) {
            clearInterval(liveCountdownTimer);
            liveCountdownTimer = null;
        }
    }

    updateTick();
    liveCountdownTimer = setInterval(updateTick, 1000);
}

function renderAdsPowerPlan(plan) {
    if (!plan || !plan.has_data) return;
    currentPlanData = plan;

    // Status colors & classes
    let dotClass = "bg-emerald-400";
    let badgeClass = "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
    let textClass = "text-emerald-400";

    if (plan.status === "expired") {
        dotClass = "bg-rose-500";
        badgeClass = "bg-rose-500/15 text-rose-300 border-rose-500/30";
        textClass = "text-rose-400";
    } else if (plan.status === "critical") {
        dotClass = "bg-amber-500 animate-pulse";
        badgeClass = "bg-amber-500/20 text-amber-300 border-amber-500/40";
        textClass = "text-amber-400";
    } else if (plan.status === "expiring_soon") {
        dotClass = "bg-amber-400";
        badgeClass = "bg-amber-500/15 text-amber-300 border-amber-500/30";
        textClass = "text-amber-300";
    }

    // 1. Header Pill
    const planDot = document.getElementById('adspower-plan-dot');
    const planText = document.getElementById('adspower-plan-text');
    const planBadge = document.getElementById('adspower-plan-badge');

    if (planDot) planDot.className = `w-2.5 h-2.5 rounded-full ${dotClass}`;
    if (planText && !liveCountdownTimer) {
        if (plan.is_expired) {
            planText.textContent = "الاشتراك: منتهي الصلاحية";
            planText.className = "text-rose-400 font-bold";
        } else {
            planText.textContent = `الاشتراك: ${plan.remaining_text}`;
            planText.className = `${textClass} font-semibold`;
        }
    }
    if (planBadge) {
        planBadge.textContent = `${plan.max_profiles} ملفات`;
        planBadge.className = `px-2 py-0.5 rounded-md text-[10px] font-mono border ${badgeClass}`;
    }

    // 2. Overview Card
    const ovName = document.getElementById('overview-plan-name');
    const ovStatusBadge = document.getElementById('overview-plan-status-badge');
    const ovFee = document.getElementById('overview-plan-fee');
    const ovEmail = document.getElementById('overview-plan-email');
    const ovUid = document.getElementById('overview-plan-uid');
    const ovExpireDate = document.getElementById('overview-plan-expire-date');
    const ovQuotaText = document.getElementById('overview-plan-quota-text');
    const ovQuotaBar = document.getElementById('overview-plan-quota-bar');

    if (ovName) ovName.textContent = plan.plan_name || "خطة AdsPower";
    if (ovStatusBadge) {
        ovStatusBadge.textContent = `${plan.status_label} (${plan.remaining_text})`;
        ovStatusBadge.className = `px-3 py-0.5 rounded-full text-xs font-bold border ${badgeClass}`;
    }
    if (ovFee) ovFee.textContent = plan.fee_formatted || "--";
    if (ovEmail) ovEmail.textContent = plan.email || plan.user_name || "--";
    if (ovUid) ovUid.textContent = plan.user_id || "--";
    if (ovExpireDate) ovExpireDate.textContent = plan.expire_date_ar || plan.expire_date_iso || "--";

    const used = plan.used_profiles || 0;
    const maxP = plan.max_profiles || 12;
    const pct = Math.min(100, Math.round((used / maxP) * 100));

    if (ovQuotaText) ovQuotaText.textContent = `${used} / ${maxP} ملف (${pct}%)`;
    if (ovQuotaBar) {
        ovQuotaBar.style.width = `${pct}%`;
        if (pct >= 100) {
            ovQuotaBar.className = "h-full rounded-full bg-gradient-to-r from-amber-500 to-rose-500";
        } else {
            ovQuotaBar.className = "h-full rounded-full bg-gradient-to-r from-emerald-500 to-indigo-500";
        }
    }

    // 3. Start Live Digital Countdown Clock
    if (plan.expire_timestamp) {
        startLiveCountdown(plan.expire_timestamp);
    }
}

function showPlanDetailsModal() {
    if (!currentPlanData) {
        refreshPlanStatus(false).then(() => {
            populatePlanModal(currentPlanData);
            openModal('modal-plan-details');
        });
        return;
    }
    populatePlanModal(currentPlanData);
    openModal('modal-plan-details');
}

function populatePlanModal(plan) {
    if (!plan) return;

    const banner = document.getElementById('modal-plan-banner');
    const bTitle = document.getElementById('modal-plan-banner-title');
    const bDesc = document.getElementById('modal-plan-banner-desc');
    const bIcon = document.getElementById('modal-plan-banner-icon');

    if (banner && bTitle && bDesc) {
        if (plan.is_expired) {
            banner.className = "p-4 rounded-2xl bg-rose-500/15 border border-rose-500/30 flex items-center gap-3";
            if (bIcon) {
                bIcon.className = "text-2xl text-rose-400";
                bIcon.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
            }
            bTitle.textContent = "اشتراك AdsPower منتهي الصلاحية";
            bDesc.textContent = `انتهت صلاحية الخطة في ${plan.expire_date_ar || plan.expire_date_iso}. يرجى التجديد عبر تطبيق AdsPower.`;
        } else {
            const isWarn = plan.status === 'critical' || plan.status === 'expiring_soon';
            banner.className = isWarn
                ? "p-4 rounded-2xl bg-amber-500/15 border border-amber-500/30 flex items-center gap-3"
                : "p-4 rounded-2xl bg-emerald-500/15 border border-emerald-500/30 flex items-center gap-3";
            if (bIcon) {
                bIcon.className = isWarn ? "text-2xl text-amber-400" : "text-2xl text-emerald-400";
                bIcon.innerHTML = isWarn ? '<i class="fa-solid fa-hourglass-half"></i>' : '<i class="fa-solid fa-circle-check"></i>';
            }
            bTitle.textContent = `الاشتراك نشط (${plan.remaining_text})`;
            bDesc.textContent = `تاريخ انتهاء الاشتراك المحدد: ${plan.expire_date_ar || plan.expire_date_iso}`;
        }
    }

    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val || '--';
    };

    setVal('modal-plan-email', plan.email || plan.user_name);
    setVal('modal-plan-uid', plan.user_id);
    setVal('modal-plan-name', plan.plan_name);
    setVal('modal-plan-fee', plan.fee_formatted);
    setVal('modal-plan-exact-date', `${plan.expire_date_ar || plan.expire_date_iso} (طابع: ${plan.balance_day_raw || '--'})`);

    const used = plan.used_profiles || 0;
    const maxP = plan.max_profiles || 12;
    const pkg = plan.package_account_num || 10;
    const bonus = plan.expired_account_num || 2;
    setVal('modal-plan-profile-breakdown', `${used} مستخدم من أصل ${maxP} (حزمة: ${pkg} + إضافي: ${bonus})`);

    const pBar = document.getElementById('modal-plan-progress-bar');
    if (pBar) {
        const pct = Math.min(100, Math.round((used / maxP) * 100));
        pBar.style.width = `${pct}%`;
    }
}

async function refreshPlanStatus(manual = false) {
    try {
        const res = await fetch('/api/adspower/plan');
        const plan = await res.json();
        if (plan && plan.success) {
            renderAdsPowerPlan(plan);
            populatePlanModal(plan);
            if (manual) {
                showToast("تم تحديث بيانات خطة واشتراك AdsPower بنجاح 🔄", "success");
            }
        }
        return plan;
    } catch (e) {
        console.error("Error refreshing plan status:", e);
        if (manual) {
            showToast("تعذر تحديث بيانات الخطة من AdsPower", "error");
        }
    }
}

// ======================== PROFILES & BULK ACTIONS ========================
async function loadProfiles() {
    const tableBody = document.getElementById('profiles-table-body');
    const badge = document.getElementById('profiles-count-badge');
    const navCount = document.getElementById('nav-profile-count');
    const statOverviewProfiles = document.getElementById('stat-overview-profiles');

    try {
        const res = await fetch('/api/profiles');
        const data = await res.json();
        state.profiles = data.profiles || [];

        if (badge) badge.textContent = state.profiles.length;
        if (navCount) navCount.textContent = state.profiles.length;
        if (statOverviewProfiles) statOverviewProfiles.textContent = state.profiles.length;

        renderProfilesTable(state.profiles);
        renderAutomationProfileCheckboxes();
        populateTerminalProfileFilter();
        updatePlatformReadyCounts();
        updateBulkAssignProxyOptions();

    } catch (err) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="6" class="py-8 text-center text-rose-400">
                    خطأ أثناء تحميل الملفات: ${err.message}
                </td>
            </tr>
        `;
    }
}

function renderProfilesTable(profilesList) {
    const tableBody = document.getElementById('profiles-table-body');
    if (!profilesList || profilesList.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="6" class="py-12 text-center text-slate-500">
                    لا توجد ملفات متصفح مسجلة بعد
                </td>
            </tr>
        `;
        return;
    }

    const activeCount = profilesList.filter(p => p.is_active).length;
    const activeBadge = document.getElementById('profiles-active-count');
    if (activeBadge) activeBadge.textContent = activeCount;

    let rowsHtml = '';
    profilesList.forEach(p => {
        const isChecked = state.selectedProfileIds.has(p.user_id) ? 'checked' : '';
        const hasProxy = p.proxy_host && p.proxy_soft !== 'no_proxy';
        const isActive = !!p.is_active;
        const platformsObj = p.platforms || {};

        let platIconsHtml = '';
        if (platformsObj.facebook) platIconsHtml += `<span title="فيسبوك مهيأ" class="text-blue-400 hover:text-blue-300"><i class="fa-brands fa-facebook"></i></span>`;
        if (platformsObj.instagram) platIconsHtml += `<span title="إنستغرام مهيأ" class="text-pink-400 hover:text-pink-300"><i class="fa-brands fa-instagram"></i></span>`;
        if (platformsObj.twitter) platIconsHtml += `<span title="X / تويتر مهيأ" class="text-sky-400 hover:text-sky-300"><i class="fa-brands fa-x-twitter"></i></span>`;
        if (platformsObj.tiktok) platIconsHtml += `<span title="تيك توك مهيأ" class="text-rose-400 hover:text-rose-300"><i class="fa-brands fa-tiktok"></i></span>`;

        const proxyBadge = hasProxy
            ? `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-mono text-[11px]">
                 <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                 ${escapeHtml(p.proxy_type.toUpperCase())}: ${escapeHtml(p.proxy_host)}:${escapeHtml(p.proxy_port)}
               </span>`
            : `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-800/80 text-slate-500 text-[11px]">
                 بدون بروكسي
               </span>`;

        const activeBadge = isActive
            ? `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-400 text-xs font-bold shadow-sm shadow-emerald-500/20">
                 <span class="w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50 animate-pulse"></span>
                 يعمل الآن
               </span>`
            : `<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-800/80 text-slate-500 text-xs font-semibold">
                 مغلق
               </span>`;

        // Dynamic Single Browser Toggle Action:
        const browserActionBtn = isActive
            ? `<button onclick="stopBrowser('${escapeHtml(p.user_id)}')" class="px-3 py-1.5 rounded-xl bg-rose-600/20 hover:bg-rose-600/35 text-rose-400 border border-rose-500/30 text-xs font-bold flex items-center gap-1.5 transition-colors shadow-sm" title="إغلاق المتصفح المفتوح حالياً">
                 <i class="fa-solid fa-power-off text-[10px]"></i>
                 <span>إغلاق</span>
               </button>`
            : `<button onclick="startBrowser('${escapeHtml(p.user_id)}')" class="px-3 py-1.5 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/35 text-emerald-400 border border-emerald-500/30 text-xs font-bold flex items-center gap-1.5 transition-colors shadow-sm" title="فتح المتصفح وبدء الجلسة">
                 <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
                 <span>فتح</span>
               </button>`;

        rowsHtml += `
            <tr class="hover:bg-slate-800/40 transition-colors ${isChecked ? 'bg-indigo-950/20' : ''}">
                <td class="py-3.5 px-4 text-center">
                    <input type="checkbox" onchange="toggleProfileSelection('${escapeHtml(p.user_id)}')" ${isChecked} class="profile-checkbox rounded bg-slate-800 border-slate-700 text-emerald-500 focus:ring-0 cursor-pointer w-4 h-4">
                </td>
                <td class="py-3.5 px-4">
                    <div class="font-bold text-white text-sm flex items-center gap-2">
                        <span onclick="openProfileDetails('${escapeHtml(p.user_id)}')" class="cursor-pointer hover:text-indigo-400 hover:underline transition-colors" title="عرض تفاصيل الملف">${escapeHtml(p.name)}</span>
                        ${p.domain_name ? `<span class="px-1.5 py-0.5 rounded text-[10px] bg-indigo-500/20 text-indigo-300 font-mono">${escapeHtml(p.domain_name)}</span>` : ''}
                    </div>
                    <div class="text-[11px] text-slate-400 font-mono flex items-center gap-2 mt-0.5 flex-wrap">
                        <span>ID: ${escapeHtml(p.user_id)}</span>
                        ${p.serial_number ? `<span class="text-slate-600">•</span><span>#${escapeHtml(p.serial_number)}</span>` : ''}
                        ${platIconsHtml ? `<span class="text-slate-600">•</span><div class="flex items-center gap-1 text-[11px]">${platIconsHtml}</div>` : ''}
                    </div>
                </td>
                <td class="py-3.5 px-4 text-slate-300">
                    <span class="px-2 py-0.5 rounded bg-slate-800/80 text-slate-300 text-[11px]">${escapeHtml(p.group_name || 'عام')}</span>
                </td>
                <td class="py-3.5 px-4">
                    <div class="flex items-center gap-2">
                        ${proxyBadge}
                        ${hasProxy ? `
                            <button onclick="removeProxyFromProfile('${escapeHtml(p.user_id)}')" title="فك ارتباط البروكسي عن هذا الملف" class="text-rose-400 hover:text-rose-300 text-xs transition-colors">
                                <i class="fa-solid fa-link-slash"></i>
                            </button>
                        ` : ''}
                    </div>
                </td>
                <td class="py-3.5 px-4 text-center">
                    ${activeBadge}
                </td>
                <td class="py-3.5 px-4 text-center">
                    <div class="flex items-center justify-center gap-1.5 flex-wrap">
                        <!-- Dynamic Primary Action -->
                        ${browserActionBtn}

                        <!-- Automation Button -->
                        <button onclick="quickSingleAutomation('${escapeHtml(p.user_id)}')" class="px-2.5 py-1.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/35 text-indigo-300 border border-indigo-500/30 text-xs font-semibold flex items-center gap-1 transition-colors" title="تشغيل أتمتة هذا الملف">
                            <i class="fa-solid fa-wand-magic-sparkles text-[10px]"></i>
                            <span>أتمتة</span>
                        </button>

                        <!-- Details Button -->
                        <button onclick="openProfileDetails('${escapeHtml(p.user_id)}')" class="px-2.5 py-1.5 rounded-xl bg-teal-600/20 hover:bg-teal-600/35 text-teal-300 border border-teal-500/30 text-xs font-semibold flex items-center gap-1 transition-colors" title="تفاصيل الملف وحسابات المنصات والبصمة">
                            <i class="fa-solid fa-id-card text-[10px]"></i>
                            <span>تفاصيل</span>
                        </button>

                        <!-- Clone Button -->
                        <button onclick="openCloneModal('${escapeHtml(p.user_id)}')" class="p-1.5 rounded-lg bg-slate-800/80 hover:bg-purple-950/60 text-slate-400 hover:text-purple-300 border border-slate-700/60 hover:border-purple-800/50 text-xs transition-colors" title="استنساخ البروفايل والكوكيز والبصمة">
                            <i class="fa-solid fa-clone text-[11px]"></i>
                        </button>

                        <!-- Export JSON Button -->
                        <button onclick="exportProfileJson('${escapeHtml(p.user_id)}')" class="p-1.5 rounded-lg bg-slate-800/80 hover:bg-teal-950/60 text-slate-400 hover:text-teal-300 border border-slate-700/60 hover:border-teal-800/50 text-xs transition-colors" title="تصدير كملف JSON">
                            <i class="fa-solid fa-file-arrow-down text-[11px]"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });

    tableBody.innerHTML = rowsHtml;
}

function filterProfiles() {
    const q = (document.getElementById('profile-search-input').value || '').toLowerCase().trim();
    if (!q) {
        renderProfilesTable(state.profiles);
        return;
    }
    const filtered = state.profiles.filter(p => {
        return (p.name && p.name.toLowerCase().includes(q)) ||
               (p.user_id && p.user_id.toLowerCase().includes(q)) ||
               (p.group_name && p.group_name.toLowerCase().includes(q)) ||
               (p.proxy_host && p.proxy_host.toLowerCase().includes(q));
    });
    renderProfilesTable(filtered);
}

// ----------------- Bulk Selections -----------------
function toggleProfileSelection(userId) {
    if (state.selectedProfileIds.has(userId)) {
        state.selectedProfileIds.delete(userId);
    } else {
        state.selectedProfileIds.add(userId);
    }
    updateFloatingBulkBar();
    renderProfilesTable(state.profiles);
}

function toggleSelectAllProfiles() {
    const chk = document.getElementById('select-all-profiles');
    if (chk.checked) {
        state.profiles.forEach(p => state.selectedProfileIds.add(p.user_id));
    } else {
        state.selectedProfileIds.clear();
    }
    updateFloatingBulkBar();
    renderProfilesTable(state.profiles);
}

function clearAllProfileSelections() {
    state.selectedProfileIds.clear();
    const chk = document.getElementById('select-all-profiles');
    if (chk) chk.checked = false;
    updateFloatingBulkBar();
    renderProfilesTable(state.profiles);
}

function updateFloatingBulkBar() {
    const bar = document.getElementById('floating-bulk-bar');
    const inTableBar = document.getElementById('bulk-actions-toolbar');
    const countText = document.getElementById('floating-selected-count');
    const inTableCountBadge = document.getElementById('bulk-selected-count-badge');
    const count = state.selectedProfileIds.size;

    if (count > 0) {
        if (bar) bar.classList.remove('hidden');
        if (inTableBar) inTableBar.classList.remove('hidden');
        if (countText) countText.textContent = `${count} ملفات`;
        if (inTableCountBadge) inTableCountBadge.textContent = `${count} ملفات محددة`;
    } else {
        if (bar) bar.classList.add('hidden');
        if (inTableBar) inTableBar.classList.add('hidden');
    }
}

async function bulkUnlinkProxySelected() {
    const userIds = Array.from(state.selectedProfileIds);
    if (!userIds.length) return;

    if (!confirm(`هل أنت متأكد من فك ارتباط البروكسي عن ${userIds.length} ملف محدد؟`)) return;

    showToast(`جاري فك ارتباط البروكسيات عن ${userIds.length} ملف...`, "info");
    try {
        const res = await fetch('/api/profiles/bulk-unlink-proxy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_ids: userIds })
        });
        const data = await res.json();
        showToast(data.message, data.success ? "success" : "error");
        loadProfiles();
        loadProxies();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

function openBulkGroupModal() {
    const count = state.selectedProfileIds.size;
    if (!count) {
        showToast("يرجى تحديد ملفات أولاً", "warning");
        return;
    }
    const countEl = document.getElementById('bulk-group-count-text');
    if (countEl) countEl.textContent = count;

    // Populate datalist with existing groups
    const datalist = document.getElementById('bulk-group-datalist');
    if (datalist) {
        const groups = new Set();
        (state.profiles || []).forEach(p => {
            if (p.group_name && p.group_name.trim()) groups.add(p.group_name.trim());
        });
        datalist.innerHTML = Array.from(groups).map(g => `<option value="${escapeHtml(g)}">`).join('');
    }

    const input = document.getElementById('bulk-group-input');
    if (input) input.value = '';

    openModal('modal-bulk-group');
}

async function submitBulkChangeGroup() {
    const userIds = Array.from(state.selectedProfileIds);
    const groupInput = document.getElementById('bulk-group-input');
    const groupName = groupInput?.value.trim() || 'الافتراضية';

    if (!userIds.length) return;

    try {
        const res = await fetch('/api/profiles/bulk-group', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_ids: userIds, group_name: groupName })
        });
        const data = await res.json();
        showToast(data.message, data.success ? "success" : "error");
        closeModal('modal-bulk-group');
        loadProfiles();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

async function exportFullBackup() {
    showToast("جاري تحضير واستخراج النسخة الاحتياطية الشاملة لكافة الملفات والكوكيز والبصمات... ⏳", "info");
    try {
        const res = await fetch('/api/profiles/bulk-export?download=false', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        if (!data.success || !data.package) {
            showToast(data.message || "فشل إنشاء النسخة الاحتياطية", "error");
            return;
        }

        const pkg = data.package;
        const total = pkg.total_profiles || 0;
        const nowStr = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        const fileName = `adspower_full_backup_${total}_profiles_${nowStr}.json`;

        const blob = new Blob([JSON.stringify(pkg, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showToast(`تم تنزيل النسخة الاحتياطية الشاملة (${total} ملفات) بنجاح! 💾`, "success");
    } catch (err) {
        showToast(`خطأ أثناء تنزيل النسخة الاحتياطية: ${err.message}`, "error");
    }
}

async function bulkExportSelected() {
    const userIds = Array.from(state.selectedProfileIds);
    if (!userIds.length) {
        showToast("يرجى تحديد ملف واحد على الأقل", "warning");
        return;
    }

    showToast(`جاري استخراج حزمة النسخ الاحتياطي لـ ${userIds.length} ملف محدد... ⏳`, "info");
    try {
        const res = await fetch('/api/profiles/bulk-export?download=false', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_ids: userIds })
        });
        const data = await res.json();
        if (!data.success || !data.package) {
            showToast(data.message || "فشل إنشاء حزمة النسخ الاحتياطي", "error");
            return;
        }

        const pkg = data.package;
        const total = pkg.total_profiles || userIds.length;
        const nowStr = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        const fileName = `adspower_backup_selected_${total}_profiles_${nowStr}.json`;

        const blob = new Blob([JSON.stringify(pkg, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showToast(`تم تنزيل حزمة النسخ الاحتياطي (${total} ملفات) بنجاح! 💾`, "success");
    } catch (err) {
        showToast(`خطأ أثناء تنزيل الحزمة: ${err.message}`, "error");
    }
}

async function bulkStartSelectedBrowsers() {
    const userIds = Array.from(state.selectedProfileIds);
    if (!userIds.length) return;

    showToast(`جاري تشغيل ${userIds.length} متصفحات بجدولة آمنة لتفادي قيود AdsPower... ⏳`, "info");
    try {
        const res = await fetch('/api/profiles/bulk-start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_ids: userIds })
        });
        const data = await res.json();
        showToast(data.message, data.success ? "success" : "warning");
        loadProfiles();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

async function bulkStopSelectedBrowsers() {
    const userIds = Array.from(state.selectedProfileIds);
    if (!userIds.length) return;

    showToast(`جاري إغلاق ${userIds.length} متصفح...`, "info");
    try {
        const res = await fetch('/api/profiles/bulk-stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_ids: userIds })
        });
        const data = await res.json();
        showToast(data.message, "success");
        loadProfiles();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

function openBulkAssignProxyModal() {
    const count = state.selectedProfileIds.size;
    if (!count) {
        showToast("يرجى تحديد ملفات أولاً", "warning");
        return;
    }
    const countEl = document.getElementById('bulk-assign-count-text');
    if (countEl) countEl.textContent = count;
    openModal('modal-bulk-assign-proxy');
}

async function submitBulkAssignProxy() {
    const proxyId = document.getElementById('bulk-assign-proxy-select').value;
    const userIds = Array.from(state.selectedProfileIds);

    if (!proxyId) {
        showToast("يرجى اختيار بروكسي من القائمة", "warning");
        return;
    }

    try {
        const res = await fetch('/api/profiles/bulk-proxy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_ids: userIds, proxy_id: proxyId })
        });
        const data = await res.json();
        showToast(data.message, "success");
        closeModal('modal-bulk-assign-proxy');
        loadProfiles();
        loadProxies();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

function sendSelectedToAutomation() {
    // Copy selected profiles to automation target list
    state.selectedAutomationProfileIds = new Set(state.selectedProfileIds);
    renderAutomationProfileCheckboxes();
    switchTab('automation');
    showToast(`تم نقل ${state.selectedAutomationProfileIds.size} ملفات للأتمتة المجمعة`, "success");
}

function quickSingleAutomation(userId) {
    state.selectedAutomationProfileIds.clear();
    state.selectedAutomationProfileIds.add(userId);
    renderAutomationProfileCheckboxes();
    switchTab('automation');
    showToast(`تم تحديد الملف ${userId} للأتمتة`, "info");
}

// ----------------- Profile Actions -----------------
async function startBrowser(userId) {
    showToast(`جاري تشغيل المتصفح للملف ${userId}...`, "info");
    try {
        const res = await fetch(`/api/profiles/${userId}/start`, { method: 'POST' });
        const data = await res.json();
        showToast(data.message, data.success ? "success" : "error");
        loadProfiles();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

async function stopBrowser(userId) {
    try {
        const res = await fetch(`/api/profiles/${userId}/stop`, { method: 'POST' });
        const data = await res.json();
        showToast(data.message, data.success ? "success" : "error");
        loadProfiles();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

async function removeProxyFromProfile(userId) {
    if (!confirm(`هل تريد فك ارتباط البروكسي من الملف ${userId}؟`)) return;
    try {
        const res = await fetch(`/api/profiles/${userId}/proxy`, { method: 'DELETE' });
        const data = await res.json();
        showToast(data.message, "success");
        loadProfiles();
        loadProxies();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

async function submitAddCustomProfile() {
    const userId = document.getElementById('modal-profile-userid').value.trim();
    const name = document.getElementById('modal-profile-name').value.trim();
    const group = document.getElementById('modal-profile-group').value.trim();

    if (!userId) {
        showToast("يرجى إدخال معرف الملف (Profile ID)", "warning");
        return;
    }

    try {
        const res = await fetch('/api/profiles/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, name: name, group_name: group })
        });
        const data = await res.json();
        showToast(data.message, data.success ? "success" : "error");
        if (data.success) {
            closeModal('modal-add-profile');
            document.getElementById('modal-profile-userid').value = '';
            document.getElementById('modal-profile-name').value = '';
            document.getElementById('modal-profile-group').value = '';
            loadProfiles();
        }
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

// ======================== MULTI-PROFILE AUTOMATION ========================
function handleAutoProfileSearch(val) {
    state.autoProfileSearchQuery = (val || '').toLowerCase().trim();
    renderAutomationProfileCheckboxes();
}

function setAutoProfileFilter(mode) {
    state.autoProfileFilterMode = mode;
    ['all', 'active', 'ready'].forEach(m => {
        const el = document.getElementById(`auto-filter-pill-${m}`);
        if (el) {
            if (m === mode) {
                el.className = 'px-2 py-0.5 rounded-lg bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 font-semibold text-[10px] transition-colors';
            } else {
                el.className = 'px-2 py-0.5 rounded-lg bg-slate-900 text-slate-400 hover:text-white border border-slate-800 font-semibold text-[10px] transition-colors';
            }
        }
    });
    renderAutomationProfileCheckboxes();
}

function isProfileReadyForPlatform(p, plat) {
    if (!p) return false;
    if (plat === 'twitter') return true; // Twitter defaults to /i/chat inbox
    const platObj = (p.platforms || {})[plat];
    return !!(platObj && platObj.post_url && platObj.post_url.trim());
}

function updatePlatformReadyCounts() {
    const platforms = ['facebook', 'instagram', 'twitter', 'tiktok'];
    platforms.forEach(plat => {
        const readyCount = (state.profiles || []).filter(p => isProfileReadyForPlatform(p, plat)).length;
        const badge = document.getElementById(`platform-ready-badge-${plat}`);
        if (badge) {
            badge.textContent = `${readyCount} جاهز`;
        }
    });
}

function updateStartAutomationButtonText() {
    const btnText = document.getElementById('btn-start-automation-text');
    if (!btnText) return;
    const n = state.selectedAutomationProfileIds.size;
    if (n === 0) {
        btnText.textContent = 'بدء الأتمتة للملفات المحددة';
        return;
    }
    const plat = state.selectedPlatform || 'facebook';
    const platNames = { facebook: 'فيسبوك', instagram: 'إنستغرام', twitter: 'X', tiktok: 'تيك توك' };
    const platName = platNames[plat] || plat;

    let activeCount = 0;
    state.selectedAutomationProfileIds.forEach(id => {
        const found = (state.profiles || []).find(p => p.user_id === id);
        if (found && found.is_active) activeCount++;
    });
    const inactiveCount = n - activeCount;

    if (inactiveCount > 0 && activeCount > 0) {
        btnText.textContent = `بدء أتمتة ${platName} (${n} ملف • ${activeCount} نشط • ${inactiveCount} سيفتح)`;
    } else if (inactiveCount > 0) {
        btnText.textContent = `بدء أتمتة ${platName} (${n} ملف سيفتح بتتابع)`;
    } else {
        btnText.textContent = `بدء أتمتة ${platName} (${n} ملف نشط)`;
    }
}

function renderAutomationProfileCheckboxes() {
    const container = document.getElementById('automation-profile-checkboxes');
    if (!container) return;

    updatePlatformReadyCounts();

    const allProfiles = state.profiles || [];
    if (allProfiles.length === 0) {
        container.innerHTML = '<div class="text-xs text-slate-500 py-3 text-center">لا توجد ملفات متوفرة</div>';
        updateAutoSelectedBadge();
        updateStartAutomationButtonText();
        return;
    }

    const curPlat = state.selectedPlatform || 'facebook';

    // Counts for filter pills
    const countAll = allProfiles.length;
    const countActive = allProfiles.filter(p => !!p.is_active).length;
    const countReady = allProfiles.filter(p => isProfileReadyForPlatform(p, curPlat)).length;

    const countAllEl = document.getElementById('auto-filter-count-all');
    const countActiveEl = document.getElementById('auto-filter-count-active');
    const countReadyEl = document.getElementById('auto-filter-count-ready');
    if (countAllEl) countAllEl.textContent = countAll;
    if (countActiveEl) countActiveEl.textContent = countActive;
    if (countReadyEl) countReadyEl.textContent = countReady;

    // Filter profiles based on filter mode and search query
    const filtered = allProfiles.filter(p => {
        if (state.autoProfileFilterMode === 'active' && !p.is_active) return false;
        if (state.autoProfileFilterMode === 'ready' && !isProfileReadyForPlatform(p, curPlat)) return false;

        if (state.autoProfileSearchQuery) {
            const q = state.autoProfileSearchQuery;
            const name = (p.name || '').toLowerCase();
            const uid = (p.user_id || '').toLowerCase();
            const grp = (p.group_name || '').toLowerCase();
            if (!name.includes(q) && !uid.includes(q) && !grp.includes(q)) return false;
        }
        return true;
    });

    if (filtered.length === 0) {
        container.innerHTML = '<div class="text-xs text-slate-500 py-4 text-center italic">لا توجد ملفات مطابقة لشروط البحث أو الفلتر</div>';
        updateAutoSelectedBadge();
        updateStartAutomationButtonText();
        return;
    }

    let html = '';
    filtered.forEach(p => {
        const isChecked = state.selectedAutomationProfileIds.has(p.user_id);
        const checkedAttr = isChecked ? 'checked' : '';
        const hasProxy = p.proxy_host && p.proxy_soft !== 'no_proxy';
        const isActive = !!p.is_active;

        const platformsObj = p.platforms || {};
        const isCurPlatReady = isProfileReadyForPlatform(p, curPlat);

        let platBadgesHtml = '';
        if (platformsObj.facebook) {
            platBadgesHtml += `<span title="فيسبوك مهيأ" class="text-[9px] px-1.5 py-0.5 rounded ${curPlat === 'facebook' ? 'bg-blue-500 text-white font-bold' : 'bg-blue-950/60 text-blue-400 border border-blue-800/40'}"><i class="fa-brands fa-facebook"></i></span>`;
        }
        if (platformsObj.instagram) {
            platBadgesHtml += `<span title="إنستغرام مهيأ" class="text-[9px] px-1.5 py-0.5 rounded ${curPlat === 'instagram' ? 'bg-pink-500 text-white font-bold' : 'bg-pink-950/60 text-pink-400 border border-pink-800/40'}"><i class="fa-brands fa-instagram"></i></span>`;
        }
        if (platformsObj.twitter) {
            platBadgesHtml += `<span title="X / تويتر مهيأ" class="text-[9px] px-1.5 py-0.5 rounded ${curPlat === 'twitter' ? 'bg-sky-500 text-white font-bold' : 'bg-sky-950/60 text-sky-400 border border-sky-800/40'}"><i class="fa-brands fa-x-twitter"></i></span>`;
        }
        if (platformsObj.tiktok) {
            platBadgesHtml += `<span title="تيك توك مهيأ" class="text-[9px] px-1.5 py-0.5 rounded ${curPlat === 'tiktok' ? 'bg-rose-500 text-white font-bold' : 'bg-rose-950/60 text-rose-400 border border-rose-800/40'}"><i class="fa-brands fa-tiktok"></i></span>`;
        }

        const readinessTag = isCurPlatReady 
            ? `<span class="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-check text-[8px]"></i>جاهز</span>`
            : `<span class="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 font-semibold flex items-center gap-1" title="لم يتم حفظ رابط لهذا المنشور بعد"><i class="fa-solid fa-triangle-exclamation text-[8px]"></i>يحتاج رابط</span>`;

        html += `
            <label class="flex items-center justify-between p-2.5 rounded-xl transition-all cursor-pointer ${isChecked ? 'bg-indigo-950/30 border border-indigo-500/50 shadow-sm' : 'bg-[#0b101c] hover:bg-slate-800/60 border border-slate-800/80'}">
                <div class="flex items-center gap-2.5 min-w-0">
                    <input type="checkbox" onchange="toggleAutoProfileSelect('${escapeHtml(p.user_id)}')" ${checkedAttr} class="rounded bg-slate-800 border-slate-700 text-emerald-500 focus:ring-0 w-4 h-4 cursor-pointer shrink-0">
                    <div class="truncate">
                        <div class="text-xs font-bold text-white flex items-center gap-2 truncate">
                            <span class="truncate">${escapeHtml(p.name)}</span>
                            ${isActive ? '<span class="w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50 animate-pulse shrink-0" title="المتصفح يعمل حالياً"></span>' : '<span class="w-1.5 h-1.5 rounded-full bg-slate-600 shrink-0" title="المتصفح مغلق"></span>'}
                        </div>
                        <div class="text-[10px] text-slate-400 font-mono flex items-center gap-1.5 mt-0.5">
                            <span>${escapeHtml(p.user_id)}</span>
                            <span class="text-slate-600">•</span>
                            ${hasProxy ? '<span class="text-emerald-400 font-bold">بروكسي</span>' : '<span class="text-slate-500">مباشر</span>'}
                        </div>
                    </div>
                </div>
                <div class="flex flex-col items-end gap-1 shrink-0 mr-2">
                    <div class="flex items-center gap-1">
                        ${platBadgesHtml || '<span class="text-[9px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-500">عام</span>'}
                    </div>
                    ${readinessTag}
                </div>
            </label>
        `;
    });

    container.innerHTML = html;
    updateAutoSelectedBadge();
    updateStartAutomationButtonText();
}

function toggleAutoProfileSelect(userId) {
    if (state.selectedAutomationProfileIds.has(userId)) {
        state.selectedAutomationProfileIds.delete(userId);
    } else {
        state.selectedAutomationProfileIds.add(userId);
    }
    updateAutoSelectedBadge();
    updateStartAutomationButtonText();
}

function updateAutoSelectedBadge() {
    const badge = document.getElementById('automation-selected-count-badge');
    if (badge) {
        badge.textContent = `${state.selectedAutomationProfileIds.size} محدد`;
    }
}

function selectAllAutomationProfiles() {
    if (!state.profiles || !state.profiles.length) return;
    state.profiles.forEach(p => state.selectedAutomationProfileIds.add(p.user_id));
    renderAutomationProfileCheckboxes();
    showToast(`تم تحديد جميع الملفات (${state.profiles.length}) للأتمتة`, "info");
}

function selectReadyAutomationProfiles() {
    const curPlat = state.selectedPlatform || 'facebook';
    const readyProfiles = (state.profiles || []).filter(p => isProfileReadyForPlatform(p, curPlat));
    if (readyProfiles.length === 0) {
        showToast(`لا توجد ملفات جاهزة حالياً لمنصة [${curPlat}]`, "warning");
        return;
    }
    state.selectedAutomationProfileIds.clear();
    readyProfiles.forEach(p => state.selectedAutomationProfileIds.add(p.user_id));
    renderAutomationProfileCheckboxes();
    showToast(`تم تحديد ${readyProfiles.length} ملف جاهز للمنصة بنجاح 🎯`, "success");
}

function clearAllAutomationProfiles() {
    state.selectedAutomationProfileIds.clear();
    renderAutomationProfileCheckboxes();
    showToast("تم إلغاء تحديد كافة الملفات", "info");
}

async function fastApplyConfigToSelected() {
    const targetIds = Array.from(state.selectedAutomationProfileIds);
    if (!targetIds.length) {
        showToast("يرجى تحديد ملف واحد على الأقل من القائمة لتطبيق الإعدادات عليه", "warning");
        return;
    }

    const curPlat = state.selectedPlatform || 'facebook';
    const postUrl = document.getElementById('auto-post-url')?.value.trim() || '';
    const pageName = document.getElementById('auto-page-name')?.value.trim() || 'DheyaStore';
    const publicTpl = document.getElementById('auto-public-template')?.value || '';
    const privateTpl = document.getElementById('auto-private-template')?.value || '';
    const cdVal = document.getElementById('auto-tw-cooldown')?.value;
    const cdNum = parseFloat(cdVal);
    const cooldownHours = (!isNaN(cdNum) && cdNum >= 0 ? cdNum : 24.0);
    const interval = parseInt(document.getElementById('auto-check-interval')?.value || 35, 10);

    const btn = document.getElementById('btn-fast-apply-config');
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-amber-300"></i> جاري حفظ وتطبيق الإعدادات...';
    }

    try {
        const res = await fetch('/api/automation/bulk-apply-config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                platform: curPlat,
                profile_ids: targetIds,
                config: {
                    post_url: postUrl,
                    page_name: pageName,
                    public_reply_template: publicTpl,
                    private_dm_template: privateTpl,
                    cooldown_hours: cooldownHours,
                    check_interval_seconds: interval
                }
            })
        });
        const data = await res.json();
        if (data.success) {
            showToast(data.message || `تم تطبيق الإعدادات وحفظها على ${targetIds.length} ملف بنجاح!`, "success");
            await loadProfiles();
        } else {
            showToast(data.message || "فشل تطبيق الإعدادات", "error");
        }
    } catch (err) {
        showToast(`خطأ في التطبيق: ${err.message}`, "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

async function startMultiAutomation() {
    const targetIds = Array.from(state.selectedAutomationProfileIds);
    if (!targetIds.length) {
        showToast("يرجى تحديد ملف واحد على الأقل للتشغيل المتزامن", "warning");
        return;
    }

    const mode = state.bulkAutomationMode || 'saved';
    const plat = state.selectedPlatform || 'facebook';
    const interval = parseInt(document.getElementById('auto-check-interval')?.value || 35, 10);
    const postUrlInput = document.getElementById('auto-post-url')?.value.trim() || '';

    // Pre-flight validation: check for missing URLs in saved mode
    if (mode === 'saved' && plat !== 'twitter') {
        const missingUrl = targetIds.filter(id => {
            const p = (state.profiles || []).find(prof => prof.user_id === id);
            return !p?.platforms?.[plat]?.post_url;
        });

        if (missingUrl.length > 0) {
            if (postUrlInput) {
                showToast(`ℹ️ تنبيه: ${missingUrl.length} ملفات لا تملك رابطاً محفوظاً، سيتم استخدام الرابط المكتوب في النموذج تلقائياً كبديل.`, "info");
            } else {
                showToast(`⚠️ تنبيه: ${missingUrl.length} ملفات من المحددة ليس لديها رابط منشور محفوظ لهذه المنصة. يرجى إدخال رابط أو الضغط على 'تطبيق وحفظ سريع'`, "warning");
                return;
            }
        }
    }

    const profilesPayload = targetIds.map(id => {
        const found = state.profiles.find(p => p.user_id === id);
        return {
            id: id,
            name: found ? found.name : id
        };
    });

    let payload = {
        platform: plat,
        profiles: profilesPayload,
        check_interval_seconds: interval,
        use_saved_config: mode === 'saved'
    };

    const postUrl = postUrlInput || (plat === 'twitter' ? 'https://x.com/i/chat' : '');
    const pageName = document.getElementById('auto-page-name')?.value.trim() || "DheyaStore";
    const publicTpl = document.getElementById('auto-public-template')?.value || '';
    const privateTpl = document.getElementById('auto-private-template')?.value || '';
    const cdVal2 = document.getElementById('auto-tw-cooldown')?.value;
    const cdNum2 = parseFloat(cdVal2);
    const cooldownHours = (!isNaN(cdNum2) && cdNum2 >= 0 ? cdNum2 : 24.0);

    payload.post_url = postUrl;
    payload.page_name = pageName;
    payload.public_reply_template = publicTpl;
    payload.private_dm_template = privateTpl;
    payload.cooldown_hours = cooldownHours;

    if (mode === 'custom' && plat !== 'twitter' && !postUrl) {
        showToast("يرجى إدخال الرابط المستهدف للمنصة في النموذج الموحد", "warning");
        return;
    }

    const btn = document.getElementById('btn-start-automation');
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> جاري إطلاق المهام...';
    }

    showToast(`جاري تشغيل الأتمتة على ${targetIds.length} ملف بتتابع آمن (3 ثوانٍ) 🚀...`, "info");

    try {
        const res = await fetch('/api/automation/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        showToast(data.message, data.success ? "success" : "error");
        pollRunner();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

async function stopSingleWorker(profileId, platform) {
    try {
        const res = await fetch('/api/automation/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile_id: profileId, platform: platform })
        });
        const data = await res.json();
        showToast(data.message || `تم إيقاف مهمة ${platform} للملف ${profileId}`, data.success ? "info" : "error");
        pollRunner();
    } catch (err) {
        showToast(`خطأ في الإيقاف: ${err.message}`, "error");
    }
}

async function stopAllAutomation() {
    try {
        const res = await fetch('/api/automation/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        showToast(data.message, "info");
        pollRunner();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

async function pollRunner() {
    try {
        const res = await fetch('/api/automation/status');
        const data = await res.json();
        const isRunning = data.is_running;

        const stats = data.stats || {};
        const workers = data.workers || [];

        const terminalActive = document.getElementById('terminal-active-workers-count');
        const terminalReplies = document.getElementById('terminal-replies-count');
        const terminalDms = document.getElementById('terminal-dms-count');
        const statReplies = document.getElementById('stat-overview-replies');
        const statDms = document.getElementById('stat-overview-dms');
        const statUptime = document.getElementById('stat-overview-uptime');

        if (terminalActive) terminalActive.textContent = data.running_count || 0;
        if (terminalReplies) terminalReplies.textContent = stats.replies_sent || 0;
        if (terminalDms) terminalDms.textContent = stats.dms_sent || 0;
        if (statReplies) statReplies.textContent = stats.replies_sent || 0;
        if (statDms) statDms.textContent = stats.dms_sent || 0;
        if (statUptime) statUptime.textContent = `وقت التشغيل: ${stats.uptime || '00:00:00'}`;

        // Active Workers Panel
        const activeTasksBadge = document.getElementById('active-tasks-badge');
        const activeWorkersList = document.getElementById('active-workers-list');
        if (activeTasksBadge) {
            activeTasksBadge.textContent = `${workers.length} نشط`;
        }
        if (activeWorkersList) {
            if (workers.length === 0) {
                activeWorkersList.innerHTML = '<div class="text-[11px] text-slate-500 italic py-3 text-center">لا توجد مهام أتمتة قيد التشغيل حالياً</div>';
            } else {
                let workersHtml = '';
                const platformIcons = {
                    facebook: '<i class="fa-brands fa-facebook text-blue-500"></i>',
                    instagram: '<i class="fa-brands fa-instagram text-pink-500"></i>',
                    twitter: '<i class="fa-brands fa-x-twitter text-sky-400"></i>',
                    tiktok: '<i class="fa-brands fa-tiktok text-rose-400"></i>'
                };
                workers.forEach(w => {
                    const icon = platformIcons[w.platform] || '<i class="fa-solid fa-robot text-emerald-400"></i>';
                    const replies = w.replies_count || 0;
                    const dms = w.dms_count || 0;
                    const statusClass = w.status === 'running' 
                        ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' 
                        : (w.status === 'initializing' ? 'bg-amber-500/20 text-amber-400 border-amber-500/30' : 'bg-slate-800 text-slate-400 border-slate-700');
                    
                    workersHtml += `
                        <div class="flex items-center justify-between p-2 rounded-xl bg-slate-900/90 border border-slate-800/80 hover:border-slate-700/80 transition-all">
                            <div class="flex items-center gap-2.5">
                                <span class="text-base">${icon}</span>
                                <div>
                                    <div class="text-xs font-bold text-white flex items-center gap-1.5">
                                        <span>${escapeHtml(w.profile_name || w.profile_id)}</span>
                                        <span class="text-[10px] font-mono text-slate-500">(${escapeHtml(w.profile_id)})</span>
                                    </div>
                                    <div class="text-[10px] text-slate-400 flex items-center gap-2 mt-0.5">
                                        <span class="px-1.5 py-0.2 rounded border text-[9px] font-bold ${statusClass}">${escapeHtml(w.status)}</span>
                                        <span class="text-slate-500">•</span>
                                        <span class="text-emerald-400 font-bold">الردود: ${replies}</span>
                                        <span class="text-purple-400 font-bold">الخاص: ${dms}</span>
                                        ${w.started_at ? `<span class="text-slate-600">•</span><span class="text-[9px] font-mono text-slate-500">${escapeHtml(w.started_at.substring(11, 19))}</span>` : ''}
                                    </div>
                                </div>
                            </div>
                            <button onclick="stopSingleWorker('${escapeHtml(w.profile_id)}', '${escapeHtml(w.platform)}')" class="px-2.5 py-1 rounded-lg bg-rose-950/60 hover:bg-rose-900/80 text-rose-300 border border-rose-800/50 text-[11px] font-bold flex items-center gap-1 transition-colors shadow-sm" title="إيقاف هذه المهمة">
                                <i class="fa-solid fa-stop text-[9px]"></i>
                                <span>إيقاف</span>
                            </button>
                        </div>
                    `;
                });
                activeWorkersList.innerHTML = workersHtml;
            }
        }

        // Fetch logs with platform, profile, and text filter
        const filterPlat = document.getElementById('terminal-filter-platform')?.value || "";
        const filterProfile = document.getElementById('terminal-filter-profile')?.value || "";
        const searchWord = document.getElementById('terminal-search-input')?.value.toLowerCase().trim() || "";

        const logsRes = await fetch(`/api/automation/logs?last_id=${state.lastLogId}&platform=${filterPlat}&profile_id=${filterProfile}`);
        const logsData = await logsRes.json();
        let logs = logsData.logs || [];

        if (searchWord) {
            logs = logs.filter(l => (l.message || '').toLowerCase().includes(searchWord) || (l.profile_name || '').toLowerCase().includes(searchWord) || (l.profile_id || '').toLowerCase().includes(searchWord));
        }

        if (logs.length > 0) {
            const terminal = document.getElementById('terminal-body');
            const autoScroll = document.getElementById('auto-scroll-toggle')?.checked;

            if (state.totalLogLines === 0 && terminal) {
                terminal.innerHTML = '';
            }

            logs.forEach(log => {
                state.lastLogId = Math.max(state.lastLogId, log.id);
                state.totalLogLines++;
                state.allLogs.push(log);

                const platformIcons = {
                    facebook: '<i class="fa-brands fa-facebook text-blue-500"></i>',
                    instagram: '<i class="fa-brands fa-instagram text-pink-500"></i>',
                    twitter: '<i class="fa-brands fa-x-twitter text-sky-400"></i>',
                    tiktok: '<i class="fa-brands fa-tiktok text-rose-400"></i>'
                };
                const platIcon = platformIcons[log.platform] || '<i class="fa-solid fa-robot text-emerald-400"></i>';

                const logDiv = document.createElement('div');
                logDiv.className = 'log-line flex items-start gap-2 text-[11px]';
                logDiv.innerHTML = `
                    <span class="log-time select-none">[${escapeHtml(log.time)}]</span>
                    <span class="select-none">${platIcon}</span>
                    <span class="px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 font-mono text-[10px] select-none">${escapeHtml(log.profile_name || log.profile_id)}</span>
                    <span class="log-badge-${log.level} select-none">${log.level}</span>
                    <span class="text-slate-200 break-words flex-1">${escapeHtml(log.message)}</span>
                `;
                terminal.appendChild(logDiv);
            });

            const linesCount = document.getElementById('terminal-lines-count');
            if (linesCount) linesCount.textContent = `${state.totalLogLines} سطر`;

            if (autoScroll && terminal) {
                terminal.scrollTop = terminal.scrollHeight;
            }
        }
    } catch (err) {
        // silent
    }
}

function populateTerminalProfileFilter() {
    const sel = document.getElementById('terminal-filter-profile');
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = '<option value="">كل الملفات</option>';
    (state.profiles || []).forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.user_id;
        opt.textContent = `${p.name || p.user_id} (${p.user_id})`;
        if (opt.value === currentVal) opt.selected = true;
        sel.appendChild(opt);
    });
}

function applyTerminalFilters() {
    state.lastLogId = 0;
    state.totalLogLines = 0;
    const terminal = document.getElementById('terminal-body');
    if (terminal) terminal.innerHTML = '';
    pollRunner();
}

async function clearTerminalLogs() {
    try {
        await fetch('/api/automation/clear-logs', { method: 'POST' });
        const terminal = document.getElementById('terminal-body');
        if (terminal) terminal.innerHTML = '<div class="text-slate-500 italic">[تم مسح السجلات بنجاح...]</div>';
        state.lastLogId = 0;
        state.totalLogLines = 0;
        state.allLogs = [];
        const linesCount = document.getElementById('terminal-lines-count');
        if (linesCount) linesCount.textContent = '0 سطر';
        showToast("تم مسح السجلات", "info");
    } catch (err) {
        console.error(err);
    }
}

// ======================== PROXY MANAGER ========================
async function loadProxies() {
    const tableBody = document.getElementById('proxies-table-body');
    const navProxyCount = document.getElementById('nav-proxy-count');
    const statOverviewProxies = document.getElementById('stat-overview-proxies');

    try {
        const res = await fetch('/api/proxies');
        const data = await res.json();
        state.proxies = data.proxies || [];

        if (navProxyCount) navProxyCount.textContent = state.proxies.length;
        if (statOverviewProxies) statOverviewProxies.textContent = state.proxies.length;

        renderProxiesTable(state.proxies);
        updateBulkAssignProxyOptions();
    } catch (err) {
        console.error("Error loading proxies:", err);
    }
}

async function syncProxiesFromAdsPower() {
    showToast("جاري مزامنة كافة البروكسيات المحفوظة في AdsPower وملفاته... ⏳", "info");
    try {
        const res = await fetch('/api/proxies/sync-adspower', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, "success");
            await loadProxies();
            await loadProfiles();
        } else {
            showToast(data.message || "فشلت المزامنة", "error");
        }
    } catch (err) {
        showToast(`خطأ أثناء المزامنة: ${err.message}`, "error");
    }
}

function renderProxiesTable(proxyList) {
    const tableBody = document.getElementById('proxies-table-body');
    if (!proxyList || proxyList.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="7" class="py-12 text-center text-slate-500">
                    <i class="fa-solid fa-shield-cat text-3xl mb-2 text-slate-600"></i>
                    <div>لا توجد بروكسيات مضافة في القائمة</div>
                    <div class="mt-3 flex items-center justify-center gap-2">
                        <button onclick="syncProxiesFromAdsPower()" class="px-4 py-1.5 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30 text-xs font-bold hover:bg-amber-500/30">
                            مزامنة البروكسيات من AdsPower
                        </button>
                        <button onclick="openModal('modal-single-proxy')" class="px-4 py-1.5 rounded-xl bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-500">
                            إضافة بروكسي يدوياً
                        </button>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    let rowsHtml = '';
    proxyList.forEach(p => {
        let speedBadge = '';
        if (p.status === 'active') {
            const ms = p.latency_ms || 0;
            const colorClass = ms < 300 ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' : (ms < 800 ? 'text-amber-400 border-amber-500/30 bg-amber-500/10' : 'text-rose-400 border-rose-500/30 bg-rose-500/10');
            speedBadge = `<span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[11px] font-mono ${colorClass}" title="IP: ${escapeHtml(p.last_ip || '')}">
                <span class="w-1.5 h-1.5 rounded-full bg-current"></span>
                نشط (${ms}ms)
            </span>`;
        } else if (p.status === 'expired') {
            speedBadge = `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30 text-[11px]" title="${escapeHtml(p.error_msg || 'انتهت باقة البروكسي')}">
                <span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span>منتهي الباقة (402)
            </span>`;
        } else if (p.status === 'failed') {
            speedBadge = `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/30 text-[11px]" title="${escapeHtml(p.error_msg || 'فشل الاتصال')}">
                <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>فشل
            </span>`;
        } else {
            speedBadge = `<span class="px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 text-[11px]">لم يفحص</span>`;
        }

        const countryBadge = p.country
            ? `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-xs font-medium">
                 <i class="fa-solid fa-location-dot text-emerald-400 text-[10px]"></i>
                 <span>${escapeHtml(p.country)}</span>
               </span>`
            : `<span class="text-slate-600 text-xs">—</span>`;

        const assignedInfo = p.assigned_to
            ? `<div class="flex items-center gap-2">
                 <span class="px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 font-medium text-xs">
                   ${escapeHtml(p.assigned_profile_name || p.assigned_to)}
                 </span>
                 <button onclick="unassignProxy('${p.id}')" title="إلغاء التعيين" class="text-slate-400 hover:text-rose-400 text-xs">
                   <i class="fa-solid fa-xmark"></i>
                 </button>
               </div>`
            : `<button onclick="openAssignProxyModal('${p.id}', '${p.host}:${p.port}${p.country ? ` [${escapeHtml(p.country)}]` : ''}${p.user ? ` (${escapeHtml(p.user)})` : ''}')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold flex items-center gap-1.5 border border-slate-700 transition-colors">
                 <i class="fa-solid fa-link text-[10px] text-emerald-400"></i>
                 <span>تعيين لملف</span>
               </button>`;

        rowsHtml += `
            <tr class="hover:bg-slate-800/40 transition-colors">
                <td class="py-3.5 px-4 font-mono text-sm text-white">
                    ${escapeHtml(p.host)}:<span class="text-slate-400">${escapeHtml(p.port)}</span>
                    ${p.source ? `<div class="text-[10px] text-slate-500 font-sans mt-0.5">${escapeHtml(p.source)}</div>` : ''}
                </td>
                <td class="py-3.5 px-4">
                    ${countryBadge}
                </td>
                <td class="py-3.5 px-4 font-mono uppercase text-slate-300 text-xs">
                    <span class="px-2 py-0.5 rounded bg-slate-800">${escapeHtml(p.type)}</span>
                </td>
                <td class="py-3.5 px-4 text-slate-400 text-xs">
                    ${p.user ? `<span class="text-slate-200 font-mono">${escapeHtml(p.user)}</span>:••••` : '<span class="text-slate-600">بدون</span>'}
                </td>
                <td class="py-3.5 px-4 text-center">
                    <div id="proxy-status-cell-${p.id}">${speedBadge}</div>
                </td>
                <td class="py-3.5 px-4">
                    ${assignedInfo}
                </td>
                <td class="py-3.5 px-4 text-center">
                    <div class="flex items-center justify-center gap-2">
                        <button onclick="testProxy('${p.id}')" class="px-2.5 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 text-xs font-semibold flex items-center gap-1 transition-colors" title="فحص السرعة">
                            <i class="fa-solid fa-bolt text-[10px]"></i>
                            <span>فحص</span>
                        </button>
                        <button onclick="deleteProxy('${p.id}')" class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors" title="حذف">
                            <i class="fa-solid fa-trash-can text-xs"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });

    tableBody.innerHTML = rowsHtml;
}

function updateBulkAssignProxyOptions() {
    const sel = document.getElementById('bulk-assign-proxy-select');
    if (!sel) return;

    let opts = '<option value="">-- اختر بروكسي من القائمة --</option>';
    state.proxies.forEach(p => {
        const countryPart = p.country ? ` [${p.country}]` : '';
        const userPart = p.user ? ` (${p.user})` : '';
        const statusPart = p.assigned_profile_name ? ` [مخصص: ${p.assigned_profile_name}]` : ' [متاح]';
        opts += `<option value="${p.id}">${escapeHtml(p.host)}:${escapeHtml(p.port)}${escapeHtml(countryPart)}${escapeHtml(userPart)}${escapeHtml(statusPart)}</option>`;
    });
    sel.innerHTML = opts;
}

async function submitAddSingleProxy() {
    const host = document.getElementById('modal-proxy-host').value.trim();
    const port = document.getElementById('modal-proxy-port').value.trim();
    const type = document.getElementById('modal-proxy-type').value;
    const user = document.getElementById('modal-proxy-user').value.trim();
    const password = document.getElementById('modal-proxy-password').value.trim();
    const country = document.getElementById('modal-proxy-country') ? document.getElementById('modal-proxy-country').value.trim() : '';

    if (!host || !port) {
        showToast("يرجى إدخال العنوان والمنفذ", "warning");
        return;
    }

    try {
        const res = await fetch('/api/proxies', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ host, port, type, user, password, country })
        });
        const data = await res.json();
        showToast(data.message, data.success ? "success" : "error");
        if (data.success) {
            closeModal('modal-single-proxy');
            document.getElementById('modal-proxy-host').value = '';
            document.getElementById('modal-proxy-port').value = '';
            document.getElementById('modal-proxy-user').value = '';
            document.getElementById('modal-proxy-password').value = '';
            if (document.getElementById('modal-proxy-country')) {
                document.getElementById('modal-proxy-country').value = '';
            }
            loadProxies();
        }
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

async function submitBulkProxies() {
    const text = document.getElementById('modal-bulk-proxy-text').value.trim();
    const type = document.getElementById('modal-bulk-proxy-type').value;

    if (!text) {
        showToast("يرجى إدخال أسطر البروكسيات", "warning");
        return;
    }

    try {
        const res = await fetch('/api/proxies/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, type })
        });
        const data = await res.json();
        showToast(data.message, data.success ? "success" : "error");
        if (data.success) {
            closeModal('modal-bulk-proxy');
            document.getElementById('modal-bulk-proxy-text').value = '';
            loadProxies();
        }
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

async function testProxy(proxyId) {
    const cell = document.getElementById(`proxy-status-cell-${proxyId}`);
    if (cell) cell.innerHTML = '<span class="text-amber-400 text-xs"><i class="fa-solid fa-spinner fa-spin ml-1"></i>فحص...</span>';

    try {
        const res = await fetch(`/api/proxies/${proxyId}/test`, { method: 'POST' });
        const data = await res.json();
        showToast(data.message, data.success ? "success" : "warning");
        loadProxies();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
        loadProxies();
    }
}

function openAssignProxyModal(proxyId, hostPort) {
    document.getElementById('modal-assign-proxy-id').value = proxyId;
    document.getElementById('modal-assign-proxy-label').textContent = hostPort;
    const select = document.getElementById('modal-assign-profile-select');

    let opts = '<option value="">-- اختر ملف متصفح --</option>';
    state.profiles.forEach(p => {
        opts += `<option value="${p.user_id}">${escapeHtml(p.name)} (${p.user_id})</option>`;
    });
    select.innerHTML = opts;
    openModal('modal-assign-proxy');
}

async function submitAssignProxy() {
    const proxyId = document.getElementById('modal-assign-proxy-id').value;
    const select = document.getElementById('modal-assign-profile-select');
    const profileId = select.value;
    const profileName = select.options[select.selectedIndex]?.text || profileId;

    if (!profileId) {
        showToast("يرجى اختيار ملف", "warning");
        return;
    }

    try {
        const res = await fetch(`/api/proxies/${proxyId}/assign`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile_id: profileId, profile_name: profileName })
        });
        const data = await res.json();
        showToast(data.message, data.success ? "success" : "error");
        closeModal('modal-assign-proxy');
        loadProxies();
        loadProfiles();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

async function unassignProxy(proxyId) {
    try {
        const res = await fetch(`/api/proxies/${proxyId}/unassign`, { method: 'POST' });
        const data = await res.json();
        showToast(data.message, "success");
        loadProxies();
        loadProfiles();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

async function deleteProxy(proxyId) {
    if (!confirm("هل أنت متأكد من حذف هذا البروكسي؟")) return;
    try {
        const res = await fetch(`/api/proxies/${proxyId}`, { method: 'DELETE' });
        const data = await res.json();
        showToast(data.message, "success");
        loadProxies();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

// ======================== SETTINGS & CONFIG ========================
async function loadConfig() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        if (data.success) {
            state.config = data.config || {};
            const setApiUrl = document.getElementById('setting-api-url');
            const setApiKey = document.getElementById('setting-api-key');
            const setPort = document.getElementById('setting-port');
            if (setApiUrl) setApiUrl.value = state.config.adspower_api_url || "http://127.0.0.1:50325";
            if (setApiKey) setApiKey.value = state.config.api_key || "";
            if (setPort) setPort.value = state.config.port || 5000;
        }
    } catch (err) {
        console.error(err);
    }
}

async function saveSettings() {
    const apiUrl = document.getElementById('setting-api-url').value.trim();
    const apiKey = document.getElementById('setting-api-key').value.trim();
    const port = parseInt(document.getElementById('setting-port').value) || 5000;

    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ adspower_api_url: apiUrl, api_key: apiKey, port: port })
        });
        const data = await res.json();
        showToast(data.message, data.success ? "success" : "error");
        checkSystemStatus(true);
        loadProfiles();
    } catch (err) {
        showToast(`خطأ: ${err.message}`, "error");
    }
}

// ======================== MODAL HELPERS ========================
function openModal(id) {
    const m = document.getElementById(id);
    if (m) m.classList.remove('hidden');
}
function closeModal(id) {
    const m = document.getElementById(id);
    if (m) m.classList.add('hidden');
}

// ======================== TOAST NOTIFICATIONS ========================
function showToast(message, type = "info") {
    const container = document.getElementById('toast-container');
    if (!container) return;

    let icon = "fa-circle-info text-sky-400";
    let border = "border-sky-500/30";
    if (type === "success") {
        icon = "fa-circle-check text-emerald-400";
        border = "border-emerald-500/40";
    } else if (type === "warning") {
        icon = "fa-triangle-exclamation text-amber-400";
        border = "border-amber-500/40";
    } else if (type === "error") {
        icon = "fa-circle-xmark text-rose-400";
        border = "border-rose-500/40";
    }

    const toast = document.createElement('div');
    toast.className = `toast-item flex items-center gap-3 p-3.5 rounded-2xl bg-[#0f172a] border ${border} text-slate-100 text-xs shadow-2xl backdrop-blur-xl`;
    toast.innerHTML = `
        <i class="fa-solid ${icon} text-base shrink-0"></i>
        <span class="flex-1 font-semibold">${escapeHtml(message)}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 4500);
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// ======================== PROFILE DETAILS & 3-WINDOW AUTOMATION ========================
let activeDetailProfileId = null;

function switchPDetailTab(tab) {
    const tabs = ['twitter', 'instagram', 'facebook'];
    tabs.forEach(t => {
        const btn = document.getElementById(`pdetail-tab-btn-${t}`);
        const pane = document.getElementById(`pdetail-pane-${t}`);
        if (!btn || !pane) return;
        if (t === tab) {
            pane.classList.remove('hidden');
            if (t === 'twitter') {
                btn.className = "px-4 py-2 rounded-xl font-bold text-xs flex items-center gap-2 transition-all bg-sky-600 text-white shadow-lg shadow-sky-600/20";
            } else if (t === 'instagram') {
                btn.className = "px-4 py-2 rounded-xl font-bold text-xs flex items-center gap-2 transition-all bg-pink-600 text-white shadow-lg shadow-pink-600/20";
            } else if (t === 'facebook') {
                btn.className = "px-4 py-2 rounded-xl font-bold text-xs flex items-center gap-2 transition-all bg-blue-600 text-white shadow-lg shadow-blue-600/20";
            }
        } else {
            pane.classList.add('hidden');
            btn.className = "px-4 py-2 rounded-xl font-bold text-xs flex items-center gap-2 transition-all bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800/80";
        }
    });
}

async function openProfileDetails(userId) {
    activeDetailProfileId = userId;
    const modal = document.getElementById('modal-profile-details');
    if (!modal) return;

    openModal('modal-profile-details');
    switchPDetailTab('twitter');

    document.getElementById('pdetail-title-name').textContent = "جاري التحميل...";
    document.getElementById('pdetail-val-id').textContent = userId;
    document.getElementById('pdetail-val-group').textContent = "--";
    document.getElementById('pdetail-current-id').value = userId;

    await loadProfileDetailsFull(userId);
}

// Populates form input values ONLY ONCE when opening modal or on explicit save/reset
async function loadProfileDetailsFull(userId) {
    if (!userId) userId = activeDetailProfileId;
    if (!userId) return;

    try {
        const res = await fetch(`/api/profiles/${userId}/details`);
        const data = await res.json();
        if (!data.success || !data.details) return;

        const d = data.details;

        // Header info
        document.getElementById('pdetail-title-name').textContent = d.name || `Profile_${userId}`;
        document.getElementById('pdetail-val-id').textContent = d.profile_id;
        document.getElementById('pdetail-val-group').textContent = d.group_name || 'الافتراضية';

        // Platform Usernames
        const u = d.usernames || {};
        const uInsta = document.getElementById('pdetail-u-insta');
        if (uInsta) uInsta.value = u.instagram || '';
        const uFb = document.getElementById('pdetail-u-fb');
        if (uFb) uFb.value = u.facebook || '';
        const uTw = document.getElementById('pdetail-u-tw');
        if (uTw) uTw.value = u.twitter || '';

        // Instagram Automations Inputs
        const ig = d.platforms?.instagram || {};
        const igUrl = document.getElementById('pdetail-insta-url');
        if (igUrl) igUrl.value = ig.post_url || '';
        const igReply = document.getElementById('pdetail-insta-reply');
        if (igReply) igReply.value = ig.public_reply_template || '';
        const igDm = document.getElementById('pdetail-insta-dm');
        if (igDm) igDm.value = ig.private_dm_template || '';

        // Facebook Automations Inputs
        const fb = d.platforms?.facebook || {};
        const fbUrl = document.getElementById('pdetail-fb-url');
        if (fbUrl) fbUrl.value = fb.post_url || '';
        const fbPage = document.getElementById('pdetail-fb-page-name');
        if (fbPage) fbPage.value = fb.page_name || u.facebook || '';
        const fbReply = document.getElementById('pdetail-fb-reply');
        if (fbReply) fbReply.value = fb.public_reply_template || '';
        const fbDm = document.getElementById('pdetail-fb-dm');
        if (fbDm) fbDm.value = fb.private_dm_template || '';
        const fbAct = fb.action_type || 'reply_and_dm';
        setPDetailFbActionType(fbAct);
        const fbInt = document.getElementById('pdetail-fb-interval');
        if (fbInt) fbInt.value = (fb.check_interval_seconds !== undefined ? fb.check_interval_seconds : 35);
        const fbMax = document.getElementById('pdetail-fb-max-replies');
        if (fbMax) fbMax.value = (fb.max_replies_per_hour !== undefined ? fb.max_replies_per_hour : 30);
        const fbCd = document.getElementById('pdetail-fb-cooldown');
        if (fbCd) fbCd.value = (fb.cooldown_hours !== undefined ? fb.cooldown_hours : 24);

        // Twitter / X DM Automations Inputs
        const tw = d.platforms?.twitter || {};
        const twUrl = document.getElementById('pdetail-tw-url');
        if (twUrl) twUrl.value = tw.post_url || 'https://x.com/i/chat';
        const twReply = document.getElementById('pdetail-tw-reply');
        if (twReply) twReply.value = tw.dm_template || tw.private_dm_template || tw.public_reply_template || 'مرحباً بك! شكراً لتواصلك معنا، نسعد بخدمتك دائماً 💬✨';
        const twCd = document.getElementById('pdetail-tw-cooldown');
        if (twCd) twCd.value = (tw.cooldown_hours !== undefined ? tw.cooldown_hours : 24);
        const twMax = document.getElementById('pdetail-tw-max-replies');
        if (twMax) twMax.value = (tw.max_replies_per_hour !== undefined ? tw.max_replies_per_hour : 25);
        const twInt = document.getElementById('pdetail-tw-interval');
        if (twInt) twInt.value = (tw.check_interval_seconds !== undefined ? tw.check_interval_seconds : 12);
        const twBatch = document.getElementById('pdetail-tw-batch-limit');
        if (twBatch) twBatch.value = (tw.batch_limit !== undefined ? tw.batch_limit : 6);
        const twReq = document.getElementById('pdetail-tw-check-requests');
        if (twReq) twReq.checked = (tw.check_requests !== undefined ? !!tw.check_requests : true);
        const twSkip = document.getElementById('pdetail-tw-skip-outgoing');
        if (twSkip) twSkip.checked = (tw.skip_if_last_outgoing !== undefined ? !!tw.skip_if_last_outgoing : true);

        // Update status badges
        updateProfileDetailsStatus(d);

    } catch (err) {
        console.error("Error loading profile details:", err);
    }
}

// Background polling: updates ONLY status badges, never touches form inputs
async function pollProfileDetailsStatus(userId) {
    if (!userId) userId = activeDetailProfileId;
    if (!userId) return;

    try {
        const res = await fetch(`/api/profiles/${userId}/details`);
        const data = await res.json();
        if (!data.success || !data.details) return;
        updateProfileDetailsStatus(data.details);
    } catch (err) {
        console.error("Error polling profile status:", err);
    }
}

// Alias for backward compatibility
async function refreshProfileDetailsData(userId) {
    return pollProfileDetailsStatus(userId);
}

function updateProfileDetailsStatus(d) {
    const cookiesEl = document.getElementById('pdetail-val-cookies');
    if (cookiesEl) {
        cookiesEl.textContent = `${d.cookies_count || 0} كوكيز`;
    }

    const fpEl = document.getElementById('pdetail-val-fingerprint');
    if (fpEl) {
        if (d.fingerprint) {
            const os = (d.fingerprint.os || 'OS').toUpperCase();
            const gpu = d.fingerprint.webgl?.unmasked_renderer || '';
            const shortGpu = gpu.length > 22 ? gpu.substring(0, 19) + '...' : gpu;
            fpEl.textContent = shortGpu ? `${os} • ${shortGpu}` : os;
            fpEl.title = d.fingerprint.summary || `${os} | ${gpu}`;
        } else {
            fpEl.textContent = 'الافتراضية';
        }
    }

    // Browser active state badge & buttons
    const badge = document.getElementById('pdetail-badge-active');
    const btnStartBrowser = document.getElementById('pdetail-btn-start-browser');
    const btnStopBrowser = document.getElementById('pdetail-btn-stop-browser');

    if (d.is_active) {
        badge.className = "text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center gap-1.5";
        badge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span><span>المتصفح مفتوح (نشط)</span>';
        btnStartBrowser.classList.add('opacity-50', 'pointer-events-none');
        btnStopBrowser.classList.remove('opacity-50', 'pointer-events-none');
    } else {
        badge.className = "text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400";
        badge.textContent = "المتصفح مغلق";
        btnStartBrowser.classList.remove('opacity-50', 'pointer-events-none');
        btnStopBrowser.classList.add('opacity-50', 'pointer-events-none');
    }

    // Proxy connection info
    const proxyBadge = document.getElementById('pdetail-proxy-badge');
    const proxySelect = document.getElementById('pdetail-proxy-select');
    const p = d.proxy || {};

    if (p.has_proxy) {
        proxyBadge.className = "text-[10px] font-bold px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-mono";
        proxyBadge.textContent = `${(p.proxy_type || 'HTTP').toUpperCase()}: ${p.proxy_host}:${p.proxy_port}`;
    } else {
        proxyBadge.className = "text-[10px] font-bold px-2 py-0.5 rounded-md bg-slate-800 text-slate-400";
        proxyBadge.textContent = "بدون بروكسي (Direct)";
    }

    // Populate proxy options if select is empty or needs update
    if (proxySelect && (!proxySelect.options || proxySelect.options.length <= 1)) {
        const currentProxyKey = p.has_proxy ? `${p.proxy_host}:${p.proxy_port}` : '';
        let optHtml = '<option value="">-- بدون بروكسي (Direct Connection) --</option>';
        (d.available_proxies || []).forEach(px => {
            const pxKey = `${px.host}:${px.port}`;
            const isSel = (currentProxyKey && pxKey === currentProxyKey) ? 'selected' : '';
            optHtml += `<option value="${px.id}" ${isSel}>${px.type.toUpperCase()}: ${px.host}:${px.port} (${px.country || px.user || 'عام'})</option>`;
        });
        proxySelect.innerHTML = optHtml;
    }

    // Platform status badges
    const ig = d.platforms?.instagram || {};
    const fb = d.platforms?.facebook || {};
    const tw = d.platforms?.twitter || {};

    updatePlatformStatusBadge('insta', ig.status);
    updatePlatformStatusBadge('fb', fb.status);
    updatePlatformStatusBadge('tw', tw.status);

    const histBadge = document.getElementById('pdetail-tw-history-badge');
    if (histBadge) {
        const count = tw.history_count !== undefined ? tw.history_count : 0;
        histBadge.textContent = `${count} معرف مسجل بالذاكرة (Cooldown)`;
    }

    const fbHistBadge = document.getElementById('pdetail-fb-history-badge');
    if (fbHistBadge) {
        const count = fb.history_count !== undefined ? fb.history_count : 0;
        fbHistBadge.textContent = `${count} تعليق مسجل بالذاكرة`;
    }
}

function updatePlatformStatusBadge(prefix, statusObj) {
    const statusBadge = document.getElementById(`pdetail-status-${prefix}`);
    const tabBadge = document.getElementById(`pdetail-tab-badge-${prefix}`);
    const btnStart = document.getElementById(`pdetail-btn-start-${prefix}`);
    const btnStop = document.getElementById(`pdetail-btn-stop-${prefix}`);

    const isRunning = statusObj && statusObj.is_running;
    if (isRunning) {
        if (statusBadge) {
            statusBadge.className = "text-xs font-bold px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5";
            statusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span><span>${escapeHtml(statusObj.status || 'نشط')}</span>`;
        }
        if (tabBadge) {
            tabBadge.className = "text-[9.5px] px-2 py-0.5 rounded-full bg-emerald-500/30 text-emerald-300 font-mono flex items-center gap-1";
            tabBadge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span><span>نشط</span>';
        }
        if (btnStart) btnStart.classList.add('opacity-50', 'pointer-events-none');
        if (btnStop) btnStop.classList.remove('opacity-50', 'pointer-events-none');
    } else {
        if (statusBadge) {
            statusBadge.className = "text-xs font-bold px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400";
            statusBadge.textContent = "متوقف";
        }
        if (tabBadge) {
            tabBadge.className = "text-[9.5px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono";
            tabBadge.textContent = "متوقف";
        }
        if (btnStart) btnStart.classList.remove('opacity-50', 'pointer-events-none');
        if (btnStop) btnStop.classList.add('opacity-50', 'pointer-events-none');
    }
}

function setTwUrl(url) {
    const el = document.getElementById('pdetail-tw-url');
    if (el) {
        el.value = url;
        el.dispatchEvent(new Event('input'));
    }
}

function setTwCooldown(hours) {
    const el = document.getElementById('pdetail-tw-cooldown');
    if (el) {
        el.value = hours;
        el.dispatchEvent(new Event('input'));
        if (hours === 0 || hours === '0') {
            showToast("تم تعطيل فترة الانتظار (Cooldown: 0) - الرد على جميع الرسائل الواردة فوراً ⚡", "info");
        } else {
            showToast(`تم ضبط فترة انتظار إعادة الرد إلى ${hours} ساعة`, "info");
        }
    }
}

function setTwMaxReplies(n) {
    const el = document.getElementById('pdetail-tw-max-replies');
    if (el) {
        el.value = n;
        el.dispatchEvent(new Event('input'));
        showToast(`تم ضبط سقف الردود إلى ${n} رد/ساعة`, "info");
    }
}

function setTwInterval(sec) {
    const el = document.getElementById('pdetail-tw-interval');
    if (el) {
        el.value = sec;
        el.dispatchEvent(new Event('input'));
        showToast(`تم ضبط فترة الفحص إلى ${sec} ثانية`, "info");
    }
}

function setTwBatchLimit(n) {
    const el = document.getElementById('pdetail-tw-batch-limit');
    if (el) {
        el.value = n;
        el.dispatchEvent(new Event('input'));
        showToast(`تم ضبط دفعة الطلبات إلى ${n} طلبات`, "info");
    }
}

function insertPDetailTwVariable(tag) {
    const el = document.getElementById('pdetail-tw-reply');
    if (!el) return;
    const start = el.selectionStart || 0;
    const end = el.selectionEnd || 0;
    const val = el.value;
    el.value = val.substring(0, start) + tag + val.substring(end);
    el.focus();
    el.selectionStart = el.selectionEnd = start + tag.length;
    el.dispatchEvent(new Event('input'));
}

function insertPDetailTwPreset(presetKey) {
    const el = document.getElementById('pdetail-tw-reply');
    if (!el) return;
    const presets = {
        welcome: "مرحباً بك {name}! شكراً لتواصلك معنا، نسعد بخدمتك دائماً. كيف يمكننا مساعدتك اليوم؟ 💬✨",
        offer: "أهلاً بك {name}! يسعدنا إخبارك بتوفر عروض وخصومات مميزة اليوم لفترة محدودة 🎁. لا تتردد بالاستفسار عن أي باقة!",
        whatsapp: "أهلاً بك {name}! للتواصل الفوري والمباشر مع فريق المبيعات والدعم الفني عبر واتساب، تفضل بالرابط: wa.me/XXXXXXXXX 📲",
        support: "مرحباً {name}، تلقينا رسالتك بخصوص الدعم الفني. فريقنا يعمل على معالجة طلبك وسنوافيك بالتفاصيل فوراً 🛠️🤝"
    };
    if (presets[presetKey]) {
        el.value = presets[presetKey];
        el.dispatchEvent(new Event('input'));
        showToast("تم تطبيق القالب الجاهز بنجاح ✨", "info");
    }
}

async function saveTwitterConfigFromDetails() {
    const userId = activeDetailProfileId;
    if (!userId) return;

    const payload = {
        twitter_username: document.getElementById('pdetail-u-tw')?.value.trim() || '',
        platforms: {
            twitter: {
                post_url: document.getElementById('pdetail-tw-url')?.value.trim() || 'https://x.com/i/chat',
                dm_template: document.getElementById('pdetail-tw-reply')?.value.trim() || '',
                public_reply_template: document.getElementById('pdetail-tw-reply')?.value.trim() || '',
                private_dm_template: document.getElementById('pdetail-tw-reply')?.value.trim() || '',
                cooldown_hours: (() => {
                    const v = parseFloat(document.getElementById('pdetail-tw-cooldown')?.value);
                    return (!isNaN(v) && v >= 0) ? v : 24.0;
                })(),
                max_replies_per_hour: parseInt(document.getElementById('pdetail-tw-max-replies')?.value, 10) || 25,
                check_interval_seconds: parseInt(document.getElementById('pdetail-tw-interval')?.value, 10) || 12,
                batch_limit: parseInt(document.getElementById('pdetail-tw-batch-limit')?.value, 10) || 6,
                check_requests: document.getElementById('pdetail-tw-check-requests') ? document.getElementById('pdetail-tw-check-requests').checked : true,
                skip_if_last_outgoing: document.getElementById('pdetail-tw-skip-outgoing') ? document.getElementById('pdetail-tw-skip-outgoing').checked : true
            }
        }
    };

    try {
        const res = await fetch(`/api/profiles/${userId}/details`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast("تم حفظ كافة إعدادات أتمتة X (تويتر) للملف بنجاح 💾", "success");
            pollProfileDetailsStatus(userId);
        } else {
            showToast(data.message || "تعذر حفظ إعدادات X", "error");
        }
    } catch (err) {
        showToast("خطأ أثناء حفظ إعدادات X: " + err.message, "error");
    }
}

async function clearTwitterHistoryFromDetails() {
    const userId = activeDetailProfileId;
    if (!userId) return;

    if (!confirm("هل أنت متأكد من رغبتك في تصفير ذاكرة الردود وفترة الانتظار (Cooldown) لهذا الملف؟\nسيؤدي ذلك للسماح بالرد الفوري مجدداً على جميع المستخدمين الذين تم الرد عليهم اليوم.")) {
        return;
    }

    try {
        const res = await fetch(`/api/profiles/${userId}/twitter/clear-history`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        if (data.success) {
            showToast(data.message || "تم تصفير ذاكرة Cooldown بنجاح 🧹", "success");
            const badge = document.getElementById('pdetail-tw-history-badge');
            if (badge) badge.textContent = "0 معرف مسجل بالذاكرة (Cooldown)";
            pollProfileDetailsStatus(userId);
        } else {
            showToast(data.message || "فشل تصفير الذاكرة", "error");
        }
    } catch (err) {
        showToast("خطأ أثناء تصفير الذاكرة: " + err.message, "error");
    }
}

function setPDetailFbActionType(type) {
    const input = document.getElementById('pdetail-fb-action-type');
    if (input) input.value = type;

    const label = document.getElementById('pdetail-fb-action-type-label');
    const btnBoth = document.getElementById('btn-fb-action-both');
    const btnPublic = document.getElementById('btn-fb-action-public');
    const btnDm = document.getElementById('btn-fb-action-dm');

    const activeClasses = ['bg-blue-950/70', 'border-blue-500', 'text-blue-300'];
    const inactiveClasses = ['bg-slate-900/80', 'border-slate-800', 'text-slate-400'];

    [btnBoth, btnPublic, btnDm].forEach(btn => {
        if (!btn) return;
        activeClasses.forEach(c => btn.classList.remove(c));
        inactiveClasses.forEach(c => btn.classList.add(c));
    });

    if (type === 'public_reply_only') {
        if (label) label.textContent = 'رد عام على التعليق فقط';
        if (btnPublic) {
            inactiveClasses.forEach(c => btnPublic.classList.remove(c));
            activeClasses.forEach(c => btnPublic.classList.add(c));
        }
    } else if (type === 'dm_only') {
        if (label) label.textContent = 'رسالة ماسنجر خاصة فقط';
        if (btnDm) {
            inactiveClasses.forEach(c => btnDm.classList.remove(c));
            activeClasses.forEach(c => btnDm.classList.add(c));
        }
    } else {
        if (label) label.textContent = 'رد عام + ماسنجر خاص';
        if (btnBoth) {
            inactiveClasses.forEach(c => btnBoth.classList.remove(c));
            activeClasses.forEach(c => btnBoth.classList.add(c));
        }
    }
}

function insertPDetailFbVariable(tag, targetId) {
    const el = document.getElementById(targetId);
    if (!el) return;
    const start = el.selectionStart || 0;
    const end = el.selectionEnd || 0;
    const val = el.value;
    el.value = val.substring(0, start) + tag + val.substring(end);
    el.focus();
    el.selectionStart = el.selectionEnd = start + tag.length;
    el.dispatchEvent(new Event('input'));
}

function insertPDetailFbPreset(presetKey, targetId) {
    const el = document.getElementById(targetId);
    if (!el) return;
    const presets = {
        welcome: "أهلاً بك {name}! شكراً لتواصلك معنا، تم إرسال التفاصيل في الخاص 📩✨",
        offer: "مرحباً {name}! يسعدنا إخبارك بوجود عرض حصري وخاص بك اليوم، تواصلنا معك في الرسائل الخاصة 🏷️🎁",
        support: "أهلاً بك {name}، فريق الدعم الفني جاهز لمساعدتك! أرسلنا لك كافة المعلومات في صندوق الوارد 🛠️",
        dm_welcome: "مرحباً {name}! نسعد بخدمتك دائماً بخصوص استفسارك على المنشور، كيف يمكننا مساعدتك اليوم؟ ✨",
        dm_whatsapp: "أهلاً بك {name}! للتواصل المباشر مع خدمة العملاء والطلب عبر واتساب: wa.me/XXXXXXXXX 📲",
        dm_catalog: "أهلاً {name}! يمكنك استعراض كتالوج المنتجات والأسعار كاملة عبر الرابط التالي: https://example.com/catalog 🛍️"
    };
    if (presets[presetKey]) {
        el.value = presets[presetKey];
        el.dispatchEvent(new Event('input'));
        showToast("تم تطبيق القالب الجاهز لفيسبوك بنجاح ✨", "info");
    }
}

function setFbCooldown(hours) {
    const el = document.getElementById('pdetail-fb-cooldown');
    if (el) {
        el.value = hours;
        el.dispatchEvent(new Event('input'));
        if (hours === 0 || hours === '0') {
            showToast("تم تعطيل فترة انتظار المعلق (Cooldown: 0) - الرد على التعليقات المتكررة فوراً ⚡", "info");
        } else {
            showToast(`تم ضبط فترة انتظار المعلق إلى ${hours} ساعة`, "info");
        }
    }
}

async function saveFacebookConfigFromDetails() {
    const userId = activeDetailProfileId;
    if (!userId) return;

    const postUrl = document.getElementById('pdetail-fb-url')?.value.trim() || '';
    const pageName = document.getElementById('pdetail-fb-page-name')?.value.trim() || '';
    const publicReply = document.getElementById('pdetail-fb-reply')?.value.trim() || '';
    const privateDm = document.getElementById('pdetail-fb-dm')?.value.trim() || '';
    const actionType = document.getElementById('pdetail-fb-action-type')?.value || 'reply_and_dm';
    const checkInterval = parseInt(document.getElementById('pdetail-fb-interval')?.value, 10) || 35;
    const maxReplies = parseInt(document.getElementById('pdetail-fb-max-replies')?.value, 10) || 30;
    const cooldownHours = (() => {
        const v = parseFloat(document.getElementById('pdetail-fb-cooldown')?.value);
        return (!isNaN(v) && v >= 0) ? v : 24.0;
    })();

    const payload = {
        facebook_username: pageName || document.getElementById('pdetail-u-fb')?.value.trim() || '',
        platforms: {
            facebook: {
                post_url: postUrl,
                page_name: pageName,
                public_reply_template: publicReply,
                private_dm_template: privateDm,
                action_type: actionType,
                check_interval_seconds: checkInterval,
                max_replies_per_hour: maxReplies,
                cooldown_hours: cooldownHours
            }
        }
    };

    try {
        const res = await fetch(`/api/profiles/${userId}/details`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast("تم حفظ كافة إعدادات أتمتة Facebook للملف بنجاح 💾", "success");
            pollProfileDetailsStatus(userId);
        } else {
            showToast(data.message || "تعذر حفظ إعدادات Facebook", "error");
        }
    } catch (err) {
        showToast("خطأ أثناء حفظ إعدادات Facebook: " + err.message, "error");
    }
}

async function clearFacebookHistoryFromDetails() {
    const userId = activeDetailProfileId;
    if (!userId) return;

    if (!confirm("هل أنت متأكد من رغبتك في تصفير ذاكرة تعليقات فيسبوك لهذا الملف؟\\nسيؤدي ذلك لإعادة فحص ومعالجة التعليقات السابقة كما لو كانت جديدة.")) {
        return;
    }

    try {
        const res = await fetch(`/api/profiles/${userId}/facebook/clear-history`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        if (data.success) {
            showToast(data.message || "تم تصفير ذاكرة تعليقات فيسبوك بنجاح 🧹", "success");
            const badge = document.getElementById('pdetail-fb-history-badge');
            if (badge) badge.textContent = "0 تعليق مسجل بالذاكرة";
            pollProfileDetailsStatus(userId);
        } else {
            showToast(data.message || "فشل تصفير الذاكرة", "error");
        }
    } catch (err) {
        showToast("خطأ أثناء تصفير الذاكرة: " + err.message, "error");
    }
}

async function startBrowserFromDetails() {
    const userId = activeDetailProfileId;
    if (!userId) return;
    showToast("جاري تشغيل المتصفح...", "info");
    await startBrowser(userId);
    setTimeout(() => pollProfileDetailsStatus(userId), 1800);
}

async function stopBrowserFromDetails() {
    const userId = activeDetailProfileId;
    if (!userId) return;
    showToast("جاري إغلاق المتصفح...", "info");
    await stopBrowser(userId);
    setTimeout(() => pollProfileDetailsStatus(userId), 1800);
}

async function assignProxyFromDetails() {
    const userId = activeDetailProfileId;
    const proxySelect = document.getElementById('pdetail-proxy-select');
    const proxyId = proxySelect.value;

    if (!proxyId) {
        await removeProxyFromDetails();
        return;
    }

    try {
        const res = await fetch(`/api/proxies/${proxyId}/assign`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile_id: userId })
        });
        const data = await res.json();
        if (data.success) {
            showToast("تم ربط البروكسي بالملف بنجاح ✅", "success");
            refreshProfileDetailsData(userId);
            loadProfiles();
        } else {
            showToast(data.message || "فشل ربط البروكسي", "error");
        }
    } catch (err) {
        showToast("خطأ أثناء ربط البروكسي: " + err.message, "error");
    }
}

async function removeProxyFromDetails() {
    const userId = activeDetailProfileId;
    if (!userId) return;

    try {
        const res = await fetch(`/api/profiles/${userId}/proxy`, { method: 'DELETE' });
        const data = await res.json();
        showToast("تم فصل البروكسي عن الملف بنجاح", "info");
        refreshProfileDetailsData(userId);
        loadProfiles();
    } catch (err) {
        showToast("خطأ أثناء فصل البروكسي: " + err.message, "error");
    }
}

async function saveUsernamesFromDetails() {
    const userId = activeDetailProfileId;
    if (!userId) return;

    const insta = document.getElementById('pdetail-u-insta').value.trim();
    const fb = document.getElementById('pdetail-u-fb').value.trim();
    const tw = document.getElementById('pdetail-u-tw').value.trim();

    try {
        const res = await fetch(`/api/profiles/${userId}/details`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                instagram_username: insta,
                facebook_username: fb,
                twitter_username: tw
            })
        });
        const data = await res.json();
        if (data.success) {
            showToast("تم حفظ حسابات المنصات بنجاح 💾", "success");
        } else {
            showToast(data.message || "تعذر حفظ الحسابات", "error");
        }
    } catch (err) {
        showToast("خطأ أثناء الحفظ: " + err.message, "error");
    }
}

async function saveAllPlatformConfigsFromDetails() {
    const userId = activeDetailProfileId;
    if (!userId) return;

    const payload = {
        instagram_username: document.getElementById('pdetail-u-insta').value.trim(),
        facebook_username: document.getElementById('pdetail-u-fb').value.trim(),
        twitter_username: document.getElementById('pdetail-u-tw').value.trim(),
        platforms: {
            instagram: {
                post_url: document.getElementById('pdetail-insta-url').value.trim(),
                public_reply_template: document.getElementById('pdetail-insta-reply').value.trim(),
                private_dm_template: document.getElementById('pdetail-insta-dm').value.trim()
            },
            facebook: {
                post_url: document.getElementById('pdetail-fb-url')?.value.trim() || '',
                page_name: document.getElementById('pdetail-fb-page-name')?.value.trim() || '',
                public_reply_template: document.getElementById('pdetail-fb-reply')?.value.trim() || '',
                private_dm_template: document.getElementById('pdetail-fb-dm')?.value.trim() || '',
                action_type: document.getElementById('pdetail-fb-action-type')?.value || 'reply_and_dm',
                check_interval_seconds: parseInt(document.getElementById('pdetail-fb-interval')?.value, 10) || 35,
                max_replies_per_hour: parseInt(document.getElementById('pdetail-fb-max-replies')?.value, 10) || 30,
                cooldown_hours: (() => {
                    const v = parseFloat(document.getElementById('pdetail-fb-cooldown')?.value);
                    return (!isNaN(v) && v >= 0) ? v : 24.0;
                })()
            },
            twitter: {
                post_url: document.getElementById('pdetail-tw-url')?.value.trim() || 'https://x.com/i/chat',
                dm_template: document.getElementById('pdetail-tw-reply')?.value.trim() || '',
                public_reply_template: document.getElementById('pdetail-tw-reply')?.value.trim() || '',
                private_dm_template: document.getElementById('pdetail-tw-reply')?.value.trim() || '',
                cooldown_hours: (() => {
                    const v = parseFloat(document.getElementById('pdetail-tw-cooldown')?.value);
                    return (!isNaN(v) && v >= 0) ? v : 24.0;
                })(),
                max_replies_per_hour: parseInt(document.getElementById('pdetail-tw-max-replies')?.value, 10) || 25,
                check_interval_seconds: parseInt(document.getElementById('pdetail-tw-interval')?.value, 10) || 12,
                batch_limit: parseInt(document.getElementById('pdetail-tw-batch-limit')?.value, 10) || 6,
                check_requests: document.getElementById('pdetail-tw-check-requests') ? document.getElementById('pdetail-tw-check-requests').checked : true,
                skip_if_last_outgoing: document.getElementById('pdetail-tw-skip-outgoing') ? document.getElementById('pdetail-tw-skip-outgoing').checked : true
            }
        }
    };

    try {
        const res = await fetch(`/api/profiles/${userId}/details`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast("تم حفظ كافة إعدادات وروابط المنصات بنجاح 💾", "success");
            pollProfileDetailsStatus(userId);
        } else {
            showToast(data.message || "تعذر حفظ الإعدادات", "error");
        }
    } catch (err) {
        showToast("خطأ أثناء الحفظ: " + err.message, "error");
    }
}

async function runPlatformFromDetails(platform) {
    const userId = activeDetailProfileId;
    if (!userId) return;

    let postUrl = '';
    let publicReply = '';
    let privateDm = '';
    let pageName = '';
    let actionType = 'reply_and_dm';
    let cooldownHours = 24.0;
    let checkInterval = 35;
    let maxReplies = 25;
    let batchLimit = 6;
    let checkRequests = true;
    let skipOutgoing = true;

    if (platform === 'instagram') {
        postUrl = document.getElementById('pdetail-insta-url').value.trim();
        publicReply = document.getElementById('pdetail-insta-reply').value.trim();
        privateDm = document.getElementById('pdetail-insta-dm').value.trim();
        checkInterval = 30;
    } else if (platform === 'facebook') {
        postUrl = document.getElementById('pdetail-fb-url')?.value.trim() || '';
        publicReply = document.getElementById('pdetail-fb-reply')?.value.trim() || '';
        privateDm = document.getElementById('pdetail-fb-dm')?.value.trim() || '';
        pageName = document.getElementById('pdetail-fb-page-name')?.value.trim() || document.getElementById('pdetail-u-fb')?.value.trim() || '';
        actionType = document.getElementById('pdetail-fb-action-type')?.value || 'reply_and_dm';
        checkInterval = parseInt(document.getElementById('pdetail-fb-interval')?.value, 10) || 35;
        maxReplies = parseInt(document.getElementById('pdetail-fb-max-replies')?.value, 10) || 30;
        cooldownHours = (() => {
            const v = parseFloat(document.getElementById('pdetail-fb-cooldown')?.value);
            return (!isNaN(v) && v >= 0) ? v : 24.0;
        })();
    } else if (platform === 'twitter') {
        postUrl = document.getElementById('pdetail-tw-url')?.value.trim() || 'https://x.com/i/chat';
        publicReply = document.getElementById('pdetail-tw-reply')?.value.trim() || 'مرحباً بك! شكراً لتواصلك معنا، نسعد بخدمتك دائماً 💬✨';
        privateDm = publicReply;
        cooldownHours = (() => {
            const v = parseFloat(document.getElementById('pdetail-tw-cooldown')?.value);
            return (!isNaN(v) && v >= 0) ? v : 24.0;
        })();
        checkInterval = parseInt(document.getElementById('pdetail-tw-interval')?.value, 10) || 12;
        maxReplies = parseInt(document.getElementById('pdetail-tw-max-replies')?.value, 10) || 25;
        batchLimit = parseInt(document.getElementById('pdetail-tw-batch-limit')?.value, 10) || 6;
        checkRequests = document.getElementById('pdetail-tw-check-requests') ? document.getElementById('pdetail-tw-check-requests').checked : true;
        skipOutgoing = document.getElementById('pdetail-tw-skip-outgoing') ? document.getElementById('pdetail-tw-skip-outgoing').checked : true;
    }

    if (!postUrl && platform !== 'twitter') {
        showToast(`يرجى إدخال رابط المنشور لأتمتة ${platform.toUpperCase()}`, "warning");
        return;
    }

    showToast(`⏳ جاري إطلاق نافذة أتمتة [${platform.toUpperCase()}] للملف...`, "info");

    try {
        const res = await fetch(`/api/profiles/${userId}/automation/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                platform: platform,
                post_url: postUrl,
                dm_template: publicReply,
                public_reply_template: publicReply,
                private_dm_template: privateDm,
                page_name: pageName,
                action_type: actionType,
                check_interval_seconds: checkInterval,
                cooldown_hours: cooldownHours,
                max_replies_per_hour: maxReplies,
                batch_limit: batchLimit,
                check_requests: checkRequests,
                skip_if_last_outgoing: skipOutgoing
            })
        });
        const data = await res.json();
        if (data.success) {
            showToast(`🚀 تم تشغيل أتمتة [${platform.toUpperCase()}] في نافذة مخصصة بنجاح!`, "success");
            setTimeout(() => pollProfileDetailsStatus(userId), 1500);
        } else {
            showToast(data.message || "فشل بدء الأتمتة", "error");
        }
    } catch (err) {
        showToast("خطأ أثناء تشغيل الأتمتة: " + err.message, "error");
    }
}

async function stopPlatformFromDetails(platform) {
    const userId = activeDetailProfileId;
    if (!userId) return;

    showToast(`جاري إيقاف أتمتة [${platform.toUpperCase()}]...`, "info");

    try {
        const res = await fetch(`/api/profiles/${userId}/automation/stop`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ platform: platform })
        });
        const data = await res.json();
        if (data.success) {
            showToast(`تم إيقاف أتمتة [${platform.toUpperCase()}] بنجاح`, "info");
            setTimeout(() => pollProfileDetailsStatus(userId), 1500);
        } else {
            showToast(data.message || "تعذر إيقاف الأتمتة", "error");
        }
    } catch (err) {
        showToast("خطأ أثناء إيقاف الأتمتة: " + err.message, "error");
    }
}

// Auto-refresh profile status badges if modal is open (without touching form fields!)
setInterval(() => {
    const modal = document.getElementById('modal-profile-details');
    if (modal && !modal.classList.contains('hidden') && activeDetailProfileId) {
        pollProfileDetailsStatus(activeDetailProfileId);
    }
}, 3000);


// ======================== PROFILE SESSION & CLONING ========================

// 1. Export Profile to JSON
async function exportProfileJson(userId) {
    if (!userId) return;
    showToast('جاري تصدير وتحضير ملف الجلسة...', 'info');
    try {
        const res = await fetch(`/api/profiles/${userId}/export?download=false`);
        const data = await res.json();
        if (!data.success || !data.package) {
            showToast(data.message || 'فشل تصدير ملف البروفايل', 'error');
            return;
        }

        const pkg = data.package;
        const profName = pkg.profile?.name || userId;
        const safeName = profName.replace(/[^\w\u0600-\u06FF\-]/g, '_');
        const filename = `profile_${userId}_${safeName}_session.json`;

        const jsonStr = JSON.stringify(pkg, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);

        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        showToast(`تم تنزيل ملف "${filename}" بنجاح! 💾`, 'success');
    } catch (err) {
        console.error("Export error:", err);
        showToast('خطأ أثناء تحميل ملف JSON: ' + err.message, 'error');
    }
}

function exportCurrentProfileJson() {
    const id = document.getElementById('pdetail-current-id')?.value || activeDetailProfileId;
    if (id) {
        exportProfileJson(id);
    }
}

function exportCurrentProfileJsonFromClone() {
    const id = document.getElementById('clone-source-id-val')?.value;
    if (id) {
        exportProfileJson(id);
    }
}

// 2. Clone Profile
let cloneTargetMode = 'existing';

async function openCloneModal(sourceId) {
    if (!sourceId) return;

    // Find profile details
    let profile = (state.profiles || []).find(p => p.user_id === sourceId);

    document.getElementById('clone-source-id-val').value = sourceId;
    document.getElementById('clone-source-name').textContent = profile?.name || `Profile_${sourceId}`;
    document.getElementById('clone-source-id-disp').textContent = `(${sourceId})`;
    document.getElementById('clone-source-cookies-badge').textContent = 'فحص الكوكيز...';

    const hasProxy = profile?.proxy_host && profile.proxy_soft !== 'no_proxy';
    const proxyDesc = hasProxy
        ? `البروكسي: ${(profile.proxy_type || 'HTTP').toUpperCase()}://${profile.proxy_host}:${profile.proxy_port}`
        : 'البروكسي: بدون بروكسي';
    document.getElementById('clone-source-proxy-info').textContent = proxyDesc;

    // Populate target select with existing profiles EXCEPT source
    const targetSelect = document.getElementById('clone-target-profile-select');
    targetSelect.innerHTML = '';

    const otherProfiles = (state.profiles || []).filter(p => p.user_id !== sourceId);
    if (otherProfiles.length === 0) {
        targetSelect.innerHTML = '<option value="">لا توجد ملفات أخرى متاحة في AdsPower</option>';
    } else {
        otherProfiles.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.user_id;
            opt.textContent = `${p.name || p.user_id} (${p.user_id}) - [${p.group_name || 'عام'}]`;
            targetSelect.appendChild(opt);
        });
    }

    // Set default name for new profile
    const newNameInput = document.getElementById('clone-new-profile-name');
    if (newNameInput) {
        newNameInput.value = `${profile?.name || sourceId} (نسخة)`;
    }

    // Reset mode to existing
    const existingRadio = document.querySelector('input[name="clone-target-mode"][value="existing"]');
    if (existingRadio) existingRadio.checked = true;
    toggleCloneMode();

    openModal('modal-clone-profile');

    // Fetch real cookies and fingerprint for source
    try {
        const cRes = await fetch(`/api/profiles/${sourceId}/cookies`);
        const cData = await cRes.json();
        const badge = document.getElementById('clone-source-cookies-badge');
        if (badge) {
            badge.textContent = `${cData.count || 0} كوكيز نشطة`;
        }
    } catch (e) {
        console.warn(e);
    }

    try {
        const fpRes = await fetch(`/api/profiles/${sourceId}/details`);
        const fpData = await fpRes.json();
        const fpInfoEl = document.getElementById('clone-source-fingerprint-info');
        if (fpInfoEl && fpData.success && fpData.details?.fingerprint) {
            const fp = fpData.details.fingerprint;
            const os = (fp.os || 'OS').toUpperCase();
            const gpu = fp.webgl?.unmasked_renderer || '';
            const shortGpu = gpu.length > 25 ? gpu.substring(0, 22) + '...' : gpu;
            fpInfoEl.textContent = `البصمة: ${os} | ${shortGpu || 'WebGL أصلي'} (نويز مشفر)`;
        }
    } catch (e) {
        console.warn(e);
    }
}

function openCloneModalFromDetails() {
    const id = document.getElementById('pdetail-current-id')?.value || activeDetailProfileId;
    if (id) {
        closeModal('modal-profile-details');
        openCloneModal(id);
    }
}

function toggleCloneMode() {
    const radios = document.getElementsByName('clone-target-mode');
    for (const r of radios) {
        if (r.checked) {
            cloneTargetMode = r.value;
            break;
        }
    }
    const existWrap = document.getElementById('clone-existing-select-wrap');
    const newWrap = document.getElementById('clone-new-input-wrap');
    if (cloneTargetMode === 'existing') {
        existWrap?.classList.remove('hidden');
        newWrap?.classList.add('hidden');
    } else {
        existWrap?.classList.add('hidden');
        newWrap?.classList.remove('hidden');
    }
}

async function submitCloneProfile() {
    const sourceId = document.getElementById('clone-source-id-val')?.value;
    if (!sourceId) {
        showToast('معرف الملف المصدر مفقود', 'error');
        return;
    }

    const btn = document.getElementById('btn-submit-clone');
    const origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> جاري الاستنساخ...';

    const targetProfileId = document.getElementById('clone-target-profile-select')?.value;
    const targetName = document.getElementById('clone-new-profile-name')?.value?.trim();
    const copyProxy = document.getElementById('clone-opt-proxy')?.checked ?? true;
    const copyAutomations = document.getElementById('clone-opt-automations')?.checked ?? true;
    const copyFingerprint = document.getElementById('clone-opt-fingerprint')?.checked ?? true;

    if (cloneTargetMode === 'existing' && !targetProfileId) {
        showToast('يرجى اختيار الملف الهدف للاستنساخ إليه', 'error');
        btn.disabled = false;
        btn.innerHTML = origHtml;
        return;
    }

    try {
        const res = await fetch(`/api/profiles/${sourceId}/clone`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode: cloneTargetMode,
                target_profile_id: targetProfileId,
                target_name: targetName,
                copy_proxy: copyProxy,
                copy_automations: copyAutomations,
                copy_fingerprint: copyFingerprint
            })
        });
        const data = await res.json();
        if (data.success) {
            showToast(data.message || 'تم استنساخ البروفايل بنجاح!', 'success');
            closeModal('modal-clone-profile');
            await loadProfiles();
        } else {
            showToast(data.message || 'فشل استنساخ البروفايل', 'error');
        }
    } catch (err) {
        showToast('خطأ في الاتصال بالسيرفر: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = origHtml;
    }
}

// 3. Import JSON Modal
let importTargetMode = 'existing';
let selectedImportPackage = null;

function openImportModal() {
    // Populate existing profiles select
    const targetSelect = document.getElementById('import-target-profile-select');
    if (targetSelect) {
        targetSelect.innerHTML = '';
        (state.profiles || []).forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.user_id;
            opt.textContent = `${p.name || p.user_id} (${p.user_id}) - [${p.group_name || 'عام'}]`;
            targetSelect.appendChild(opt);
        });
    }

    // Reset file inputs
    const fileInput = document.getElementById('import-json-file');
    if (fileInput) fileInput.value = '';
    const fileLabel = document.getElementById('import-file-label');
    if (fileLabel) fileLabel.textContent = 'اضغط لاختيار ملف .json أو اسحبه هنا';
    const fileSummary = document.getElementById('import-file-summary');
    if (fileSummary) {
        fileSummary.classList.add('hidden');
        fileSummary.textContent = '';
    }

    // Reset bulk preview wrap & restore button
    const bulkWrap = document.getElementById('import-bulk-preview-wrap');
    if (bulkWrap) bulkWrap.classList.add('hidden');
    const singleWrap = document.getElementById('import-single-target-wrap');
    if (singleWrap) singleWrap.classList.remove('hidden');
    const btnText = document.getElementById('btn-submit-import-text');
    if (btnText) btnText.textContent = 'استيراد وتطبيق البيانات';

    selectedImportPackage = null;

    const existingRadio = document.querySelector('input[name="import-target-mode"][value="existing"]');
    if (existingRadio) existingRadio.checked = true;
    toggleImportMode();

    openModal('modal-import-profile');
}

function toggleImportMode() {
    const radios = document.getElementsByName('import-target-mode');
    for (const r of radios) {
        if (r.checked) {
            importTargetMode = r.value;
            break;
        }
    }
    const existWrap = document.getElementById('import-existing-select-wrap');
    const newWrap = document.getElementById('import-new-input-wrap');
    if (importTargetMode === 'existing') {
        existWrap?.classList.remove('hidden');
        newWrap?.classList.add('hidden');
    } else {
        existWrap?.classList.add('hidden');
        newWrap?.classList.remove('hidden');
    }
}

function getChromeDataBadgesHtml(pkg) {
    if (!pkg) return '';
    const cd = pkg.chrome_data || {};
    const sum = pkg.chrome_data_summary || {};
    const fp = pkg.fingerprint || {};
    const badges = [];

    // 1. Screen resolution badge
    const screenRes = sum.screen_resolution || pkg.screen?.resolution || fp.screen?.resolution;
    if (screenRes) {
        const cleanRes = String(screenRes).replace('_', 'x');
        badges.push(`<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-sky-500/15 text-sky-300 text-[10px] font-bold border border-sky-500/30"><i class="fa-solid fa-desktop text-[9px]"></i> شاشة ${cleanRes}</span>`);
    }

    // 2. Hardware specs badge (CPU Cores & RAM)
    const hwSummary = sum.hardware_summary || (pkg.hardware?.cpu_cores ? `${pkg.hardware.cpu_cores} Cores / ${pkg.hardware.device_memory_gb || 8}GB RAM` : (fp.hardware?.cpu_cores ? `${fp.hardware.cpu_cores} Cores` : ''));
    if (hwSummary) {
        badges.push(`<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 text-[10px] font-bold border border-amber-500/30"><i class="fa-solid fa-microchip text-[9px]"></i> عتاد ${hwSummary}</span>`);
    }

    // 3. Fonts badge
    const fontsCount = sum.fonts_count || pkg.fonts_count || (Array.isArray(pkg.fonts) ? pkg.fonts.length : 0) || (Array.isArray(fp.fonts) ? fp.fonts.length : 0);
    if (fontsCount > 0) {
        badges.push(`<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-fuchsia-500/15 text-fuchsia-300 text-[10px] font-bold border border-fuchsia-500/30"><i class="fa-solid fa-font text-[9px]"></i> ${fontsCount} خطاً</span>`);
    }

    // 4. User-Agent badge
    const uaStr = sum.user_agent || pkg.user_agent || fp.user_agent;
    if (uaStr) {
        let shortUa = 'User-Agent';
        if (uaStr.includes('Macintosh') || uaStr.includes('Mac OS')) shortUa = 'macOS';
        else if (uaStr.includes('Windows')) shortUa = 'Windows';
        else if (uaStr.includes('Linux')) shortUa = 'Linux';
        const chromeMatch = uaStr.match(/Chrome\/([0-9.]+)/);
        if (chromeMatch) shortUa += ` • Chrome ${chromeMatch[1]}`;
        const escapedUa = uaStr.replace(/"/g, '&quot;');
        badges.push(`<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-500/15 text-rose-300 text-[10px] font-bold border border-rose-500/30" title="${escapedUa}"><i class="fa-solid fa-globe text-[9px]"></i> ${shortUa}</span>`);
    }

    if (sum.has_passwords || cd.login_data) {
        badges.push('<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 text-[10px] font-bold border border-amber-500/30"><i class="fa-solid fa-key text-[9px]"></i> كلمات المرور</span>');
    }
    if (sum.has_local_storage || cd.local_storage) {
        badges.push('<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 text-[10px] font-bold border border-cyan-500/30"><i class="fa-solid fa-box-archive text-[9px]"></i> التخزين المحلي</span>');
    }
    if (sum.has_indexeddb || cd.indexeddb || cd.web_storage) {
        badges.push('<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-indigo-500/15 text-indigo-300 text-[10px] font-bold border border-indigo-500/30"><i class="fa-solid fa-database text-[9px]"></i> IndexedDB</span>');
    }
    if (sum.has_history || cd.history) {
        badges.push('<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-blue-500/15 text-blue-300 text-[10px] font-bold border border-blue-500/30"><i class="fa-solid fa-clock-rotate-left text-[9px]"></i> سجل التصفح</span>');
    }
    if (sum.has_bookmarks || cd.bookmarks_raw || (cd.bookmarks && Object.keys(cd.bookmarks).length > 0)) {
        badges.push('<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-pink-500/15 text-pink-300 text-[10px] font-bold border border-pink-500/30"><i class="fa-solid fa-bookmark text-[9px]"></i> المفضلة</span>');
    }
    const extCount = sum.extensions_count || (cd.installed_extensions ? cd.installed_extensions.length : 0);
    if (sum.has_extensions || extCount > 0 || cd.local_ext_settings) {
        badges.push(`<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 text-[10px] font-bold border border-purple-500/30"><i class="fa-solid fa-puzzle-piece text-[9px]"></i> ${extCount > 0 ? extCount + ' إضافات' : 'الإضافات'}</span>`);
    }
    if (sum.has_cookies_db || cd.cookies_raw_file || cd.sf_cookie) {
        badges.push('<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 text-[10px] font-bold border border-emerald-500/30"><i class="fa-solid fa-cookie text-[9px]"></i> الكوكيز الكاملة</span>');
    }
    if (sum.has_session_storage || cd.session_storage || cd.sessions_dir) {
        badges.push('<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-teal-500/15 text-teal-300 text-[10px] font-bold border border-teal-500/30"><i class="fa-solid fa-window-maximize text-[9px]"></i> التبويبات والجلسات</span>');
    }
    return badges.join(' ');
}

function handleImportFileSelected(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            const parsed = JSON.parse(e.target.result);
            selectedImportPackage = parsed;

            const bulkWrap = document.getElementById('import-bulk-preview-wrap');
            const singleWrap = document.getElementById('import-single-target-wrap');
            const btnText = document.getElementById('btn-submit-import-text');
            const fileLabel = document.getElementById('import-file-label');
            const sumEl = document.getElementById('import-file-summary');

            // Check if this is a bulk backup package
            const isBulk = parsed.backup_type === 'adspower_bulk_backup' || Array.isArray(parsed.packages);
            if (isBulk && Array.isArray(parsed.packages)) {
                const pkgs = parsed.packages;
                if (bulkWrap) bulkWrap.classList.remove('hidden');
                if (singleWrap) singleWrap.classList.add('hidden');
                if (btnText) btnText.textContent = `استعادة كافة الملفات (${pkgs.length})`;

                const countBadge = document.getElementById('import-bulk-count-badge');
                if (countBadge) countBadge.textContent = `${pkgs.length} ملفات`;

                const listEl = document.getElementById('import-bulk-profiles-list');
                if (listEl) {
                    listEl.innerHTML = pkgs.map((p, idx) => {
                        const prof = p.profile || {};
                        const cookiesCount = p.cookies_count || (Array.isArray(p.cookies) ? p.cookies.length : 0);
                        const proxyDesc = p.proxy?.proxy_host ? `${p.proxy.proxy_host}:${p.proxy.proxy_port}` : 'بدون بروكسي';
                        const pBadges = getChromeDataBadgesHtml(p);
                        return `<div class="p-2 rounded-lg bg-slate-950/70 border border-slate-800/60 space-y-1.5">
                            <div class="flex items-center justify-between">
                                <div class="flex items-center gap-2 overflow-hidden">
                                    <span class="text-slate-500 text-[9px] w-4">${idx + 1}.</span>
                                    <span class="font-bold text-slate-200 truncate text-xs">${prof.name || prof.user_id || 'ملف'}</span>
                                    <span class="text-slate-500 text-[9px]">(${prof.user_id || '-'})</span>
                                </div>
                                <div class="flex items-center gap-2 text-[9px] shrink-0">
                                    <span class="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-bold">${cookiesCount} كوكيز</span>
                                    <span class="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">${proxyDesc}</span>
                                </div>
                            </div>
                            ${pBadges ? `<div class="flex flex-wrap gap-1 pt-0.5">${pBadges}</div>` : ''}
                        </div>`;
                    }).join('');
                }

                if (fileLabel) fileLabel.textContent = `حزمة نسخ احتياطي: ${file.name}`;
                if (sumEl) {
                    sumEl.classList.remove('hidden');
                    sumEl.innerHTML = `<div class="text-emerald-400 font-bold flex items-center gap-1.5">
                        <i class="fa-solid fa-circle-check"></i>
                        <span>حزمة نسخ احتياطي شاملة تحتوي على ${pkgs.length} ملفات مع البصمة، العتاد، الشاشة، الخطوط، كلمات المرور، التخزين المحلي، الإضافات والجلسات</span>
                    </div>`;
                }
            } else {
                // Single profile backup
                if (bulkWrap) bulkWrap.classList.add('hidden');
                if (singleWrap) singleWrap.classList.remove('hidden');
                if (btnText) btnText.textContent = 'استيراد وتطبيق البيانات';

                const cookiesCount = parsed.cookies_count || (Array.isArray(parsed.cookies) ? parsed.cookies.length : 0);
                const profName = parsed.profile?.name || file.name;
                const fpDesc = parsed.fingerprint?.summary || (parsed.fingerprint?.os ? `بصمة ${parsed.fingerprint.os.toUpperCase()}` : '');
                const badges = getChromeDataBadgesHtml(parsed);

                if (fileLabel) fileLabel.textContent = `الملف المختار: ${file.name}`;
                if (sumEl) {
                    sumEl.classList.remove('hidden');
                    sumEl.innerHTML = `
                        <div class="space-y-1.5 text-right" dir="rtl">
                            <div class="font-bold text-emerald-400 flex items-center gap-1.5">
                                <i class="fa-solid fa-circle-check text-xs"></i>
                                <span>تم التحقق من النسخة الاحتياطية: "${profName}" (${cookiesCount} كوكيز)</span>
                            </div>
                            <div class="text-[10px] text-slate-400">${fpDesc ? `البصمة الرقمية: ${fpDesc}` : ''}</div>
                            ${badges ? `<div class="flex flex-wrap gap-1.5 pt-1">${badges}</div>` : ''}
                        </div>
                    `;
                }

                const newNameInput = document.getElementById('import-new-profile-name');
                if (newNameInput && (!newNameInput.value || newNameInput.value.includes('مستورد'))) {
                    newNameInput.value = `${profName} (مستورد)`;
                }
            }
        } catch (err) {
            showToast('الملف المختار ليس بصيغة JSON صالحة', 'error');
            selectedImportPackage = null;
        }
    };
    reader.readAsText(file);
}

async function submitImportProfile() {
    if (!selectedImportPackage) {
        showToast('يرجى اختيار ملف JSON صالح أولاً', 'error');
        return;
    }

    const isBulk = selectedImportPackage.backup_type === 'adspower_bulk_backup' || Array.isArray(selectedImportPackage.packages);
    const targetProfileId = document.getElementById('import-target-profile-select')?.value;
    const targetName = document.getElementById('import-new-profile-name')?.value?.trim();
    const copyProxy = document.getElementById('import-opt-proxy')?.checked ?? true;
    const copyAutomations = document.getElementById('import-opt-automations')?.checked ?? true;
    const copyFingerprint = document.getElementById('import-opt-fingerprint')?.checked ?? true;

    if (!isBulk && importTargetMode === 'existing' && !targetProfileId) {
        showToast('يرجى اختيار البروفايل الهدف للاستيراد فوقه', 'error');
        return;
    }

    const btn = document.getElementById('btn-submit-import');
    const origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${isBulk ? 'جاري استعادة الحزمة...' : 'جاري الاستيراد...'}`;

    try {
        const payload = {
            package: selectedImportPackage,
            copy_proxy: copyProxy,
            copy_automations: copyAutomations,
            copy_fingerprint: copyFingerprint
        };

        if (!isBulk) {
            payload.target_profile_id = importTargetMode === 'existing' ? targetProfileId : null;
            payload.target_name = targetName;
        }

        const res = await fetch('/api/profiles/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast(data.message || 'تم استيراد البيانات بنجاح!', 'success');
            closeModal('modal-import-profile');
            await loadProfiles();
        } else {
            showToast(data.message || 'فشل استيراد البيانات', 'error');
        }
    } catch (err) {
        showToast('خطأ أثناء الاستيراد: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = origHtml;
    }
}

