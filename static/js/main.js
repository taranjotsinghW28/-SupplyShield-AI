// ==========================================
// GLOBAL INITIALIZATION & MEMORY STATES
// ==========================================
window.ACTIVE_HIGH_RISK_NODES = [];
window.SELECTED_TARGET_NODE_NAME = null;
window.EMAIL_RECIPIENT_DATA_CACHE = [];
window.SUPPLIER_SCAN_POLL_ID = null;
window.SCAN_CANCELLED = false;

function showToast(message, duration = 3500) {
    const container = document.getElementById("toast-container");
    if (!container) { alert(message); return; }
    const toast = document.createElement("div");
    toast.className = "toast-msg";
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(40px)";
        toast.style.transition = "all 0.3s";
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function openModal(id) {
    const el = document.getElementById(id);
    if (el) { el.classList.add("is-open"); document.body.style.overflow = "hidden"; }
}

function closeModal(id) {
    const el = document.getElementById(id);
    if (el) { el.classList.remove("is-open"); document.body.style.overflow = ""; }
}

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        closeRemediationPanel();
        closeEmailPanel();
        closePremiumCheckoutPanel();
    }
});

// ==========================================
// CORE DOM LIFECYCLE ROUTERS
// ==========================================
document.addEventListener("DOMContentLoaded", function () {
    // 1. Theme Engine Switch Synchronization
    const toggleSwitch = document.getElementById("theme-toggle-checkbox");
    const savedTheme = localStorage.getItem("theme");
    const initialTheme = savedTheme || "light";

    document.documentElement.setAttribute("data-theme", initialTheme);
    if (initialTheme === "dark" && toggleSwitch) toggleSwitch.checked = true;

    if (toggleSwitch) {
        toggleSwitch.addEventListener("change", function (e) {
            const targetTheme = e.target.checked ? "dark" : "light";
            document.documentElement.setAttribute("data-theme", targetTheme);
            localStorage.setItem("theme", targetTheme);
            if (document.getElementById("results-stage-view") && !document.getElementById("results-stage-view").classList.contains("d-none")) {
                renderDashboardMetricsCharts();
            }
        });
    }

    // 2. Infinite scroll reveal assembler
    initializeInfiniteScrollAssembler();

    // 3. Drag & Drop File Upload Workspace Setup
    initializeDragAndDropUpload();

    // 4. Trend Performance Chart Bootstrapper
    initializeHistoricalTrendsChart();

    // 5. Restore dashboard state if suppliers already exist
    initializeDashboardState();

    const cancelScanBtn = document.getElementById('cancel-scan-btn');
    if (cancelScanBtn) {
        cancelScanBtn.addEventListener('click', cancelScanAndReset);
    }

    // 6. Auto-open premium checkout when redirected from /premium or /premium-hub
    if (window.location.search.includes("upgrade=premium")) {
        setTimeout(() => openPremiumCheckoutPanel(), 400);
    }
});

// ==========================================
// INFINITE REVERSING SCROLL ASSEMBLER LOGIC
// ==========================================
function initializeInfiniteScrollAssembler() {
    const puzzlePieces = document.querySelectorAll(".reveal-on-scroll");
    
    if (puzzlePieces.length === 0) return;

    // Advanced threshold rules to catch entries at both top and bottom viewports
    const observerOptions = {
        root: null,
        rootMargin: "-4% 0px -4% 0px", 
        threshold: [0, 0.15, 0.85, 1.0] 
    };

    const scrollAssemblerObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            // If the element is nicely centered in the viewport, snap it together
            if (entry.isIntersecting && entry.intersectionRatio > 0.1) {
                entry.target.classList.add("assembled");
            } else {
                // Dissolves and deconstructs when scrolled past, ready to re-animate in reverse!
                entry.target.classList.remove("assembled");
            }
        });
    }, observerOptions);

    puzzlePieces.forEach((piece) => {
        scrollAssemblerObserver.observe(piece);
    });
}

// ==========================================
// PHASE 8: EXPORT & REPORTING UTILITIES
// ==========================================
function copyTableToClipboard() {
    const tableBody = document.getElementById("supplier-table-rows");
    if (!tableBody || tableBody.children.length === 0) {
        alert("Operation Aborted: There are no active supplier data profiles currently rendered to extract.");
        return;
    }

    let extractedTextSummary = "=== LOGISTICAL FLEET SUPPLYSHIELD RISK ANALYSIS MATRIX ===\n\n";
    extractedTextSummary += "Supplier Name ID | Category Node | Region Node | Delivery Performance | Hazard Index\n";
    extractedTextSummary += "------------------------------------------------------------------------------------\n";

    Array.from(tableBody.querySelectorAll("tr")).forEach(row => {
        const cells = row.querySelectorAll("td");
        if (cells.length >= 5) {
            extractedTextSummary += `${cells[0].innerText.trim()} | ${cells[1].innerText.trim()} | ${cells[2].innerText.trim()} | ${cells[3].innerText.trim()} | ${cells[4].innerText.trim()}\n`;
        }
    });

    navigator.clipboard.writeText(extractedTextSummary)
    .then(() => alert("🚀 Data Sync Successful: Current supplier compliance list copied to clipboard cleanly!"))
    .catch(() => alert("Clipboard Transfer Failed: Please allow browser permissions to execute copying scripts."));
}

// ==========================================
// PHASE 7: REMEDIATION WORKSPACE UI ACTIONS
// ==========================================
function openRemediationPanel() {
    const overlay = document.getElementById("remediation-overlay-panel");
    const targetsList = document.getElementById("remediation-targets-list");
    const editor = document.getElementById("remediation-ticket-editor");
    
    if (!overlay || !targetsList) return;
    
    targetsList.innerHTML = "";
    if (editor) editor.value = "";
    window.SELECTED_TARGET_NODE_NAMES = []; // Array for multi-select
    document.getElementById("remediation-dispatch-btn").disabled = true;
    
    fetch("/api/suppliers-list")
    .then(res => res.json())
    .then(suppliers => {
        window.ACTIVE_HIGH_RISK_NODES = suppliers.filter(s => s.risk_status === "High");
        
        if (window.ACTIVE_HIGH_RISK_NODES.length === 0) {
            targetsList.innerHTML = `
                <div class="text-center py-4">
                    <p class="text-success fw-bold" style="font-size:0.85rem; margin:0;">✅ All systems clear. No active high-risk nodes tracked.</p>
                </div>`;
            overlay.classList.add("is-open");
            return;
        }

        window.ACTIVE_HIGH_RISK_NODES.forEach((node) => {
            let breachReason = "Spiked hazard threshold configurations.";
            if (node.overall_on_time_rate < 85) {
                breachReason = `Critical log delays: Overall on-time performance sank to ${node.overall_on_time_rate}%.`;
            } else if (node.ai_risk_summary && node.ai_risk_summary.length > 5) {
                breachReason = "AI threat intelligence scanning flagged compliance anomalies.";
            }

            node.computed_reason = breachReason;
            const nodeItem = document.createElement("div");
            nodeItem.className = "p-2 border rounded cursor-pointer remediation-target-item";
            nodeItem.style.cssText = "background: rgba(0,0,0,0.01); border-color: var(--border-color) !important; cursor: pointer; transition: all 0.2s ease;";
            nodeItem.innerHTML = `
                <div class="form-check d-flex justify-content-between align-items-center w-100 m-0">
                    <div>
                        <input class="form-check-input remediation-checkbox" type="checkbox" value="${node.name}" id="chk-rem-${node._id}" style="margin-right: 8px; cursor: pointer;">
                        <label class="form-check-label" for="chk-rem-${node._id}" style="color: var(--text-primary); font-size:0.85rem; cursor: pointer;">
                            <strong>${node.name}</strong>
                        </label>
                    </div>
                    <span class="badge bg-danger" style="font-size:0.7rem;">${node.hazard_score}/100</span>
                </div>
                <p style="font-size: 0.75rem; color: var(--text-muted); margin: 4px 0 0 24px; line-height:1.3;">⚠️ <i>${breachReason}</i></p>`;

            nodeItem.onclick = (e) => {
                // If clicking outside the checkbox but on the item, toggle checkbox
                const checkbox = document.getElementById(`chk-rem-${node._id}`);
                if (e.target !== checkbox && e.target.tagName !== 'LABEL') {
                    checkbox.checked = !checkbox.checked;
                }
                selectRemediationTarget(node, checkbox, nodeItem);
            };
            targetsList.appendChild(nodeItem);
        });
        overlay.classList.add("is-open");
    });
}

function selectRemediationTarget(node, checkbox, element) {
    if (!window.SELECTED_TARGET_NODE_NAMES) {
        window.SELECTED_TARGET_NODE_NAMES = [];
    }
    const index = window.SELECTED_TARGET_NODE_NAMES.indexOf(node.name);
    
    if (checkbox.checked) {
        if (index === -1) window.SELECTED_TARGET_NODE_NAMES.push(node.name);
        element.style.background = "rgba(0, 85, 255, 0.05)";
        element.style.borderColor = "var(--accent-blue) !important";
    } else {
        if (index > -1) window.SELECTED_TARGET_NODE_NAMES.splice(index, 1);
        element.style.background = "rgba(0,0,0,0.01)";
        element.style.borderColor = "var(--border-color) !important";
    }
    
    const editor = document.getElementById("remediation-ticket-editor");
    if (window.SELECTED_TARGET_NODE_NAMES.length > 0) {
        document.getElementById("remediation-dispatch-btn").disabled = false;
        editor.value = `### [ESCALATION REMEDIATION INCIDENT REPORT]\n\nTarget Node Vendors: ${window.SELECTED_TARGET_NODE_NAMES.join(', ')}\n\nThreat Summary:\n- Compliance anomalies detected.\n\nPlease audit logs or execute backup procurement lines immediately.`;
    } else {
        document.getElementById("remediation-dispatch-btn").disabled = true;
        editor.value = "";
    }
}

function closeRemediationPanel() {
    closeModal("remediation-overlay-panel");
}

function draftTicketWithAI() {
    if (!window.SELECTED_TARGET_NODE_NAMES || window.SELECTED_TARGET_NODE_NAMES.length === 0) {
        alert("Operation Denied: Please highlight at least one target company node first.");
        return;
    }
    
    const editor = document.getElementById("remediation-ticket-editor");
    const aiBtn = document.getElementById("ai-draft-trigger-btn");
    
    aiBtn.disabled = true;
    aiBtn.innerHTML = `⏳ Composing...`;
    
    fetch("/api/analytics/draft-ai-ticket", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ supplier_name: window.SELECTED_TARGET_NODE_NAMES.join(',') })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) editor.value = data.ai_markdown_draft;
        else alert("AI Generation Error: " + data.message);
    })
    .catch(() => alert("Network transmission failure connecting to generative models."))
    .finally(() => {
        aiBtn.disabled = false;
        aiBtn.innerHTML = `✨ Create with AI`;
    });
}

function dispatchRemediationTickets() {
    const editor = document.getElementById("remediation-ticket-editor");
    const dispatchBtn = document.getElementById("remediation-dispatch-btn");
    
    // NEW: Gather the dynamic fields
    const payload = {
        supplier_name: window.SELECTED_TARGET_NODE_NAMES ? window.SELECTED_TARGET_NODE_NAMES.join(',') : '',
        project_id: document.getElementById('gl-project-id').value, // NEW
        access_token: document.getElementById('gl-access-token').value, // NEW
        title: document.getElementById('gl-title').value,          // NEW
        category: document.getElementById('gl-category').value,    // NEW
        severity: document.getElementById('gl-severity').value,    // NEW
        ticket_content: editor.value
    };
    
    if (!payload.supplier_name || !payload.project_id) {
        showToast("Error: Please select a node and provide a Project ID.");
        return;
    }
    
    dispatchBtn.disabled = true;
    dispatchBtn.innerHTML = `⏳ Dispatching...`;
    
    fetch("/api/analytics/dispatch-bulk-remediation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        showToast(data.message || "Ticket dispatched.");
        closeRemediationPanel();
    })
    .catch(() => {
        showToast("Dispatch failed.");
        dispatchBtn.disabled = false;
        dispatchBtn.innerHTML = `📥 Dispatch Ticket`;
    });
}

function dispatchAllHighRiskTickets() {
    const bulkBtn = document.getElementById("bulk-dispatch-all-btn");
    const projectId = document.getElementById('gl-project-id').value.trim();
    const accessToken = document.getElementById('gl-access-token').value.trim();

    if (!projectId) {
        showToast("Error: Please provide a Project ID first.");
        return;
    }

    if (!window.confirm("Create GitLab remediation tickets for ALL high-risk suppliers?")) return;

    if (bulkBtn) {
        bulkBtn.disabled = true;
        bulkBtn.textContent = "⏳ Dispatching...";
    }

    fetch("/api/analytics/dispatch-all-high-risk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, access_token: accessToken })
    })
    .then(res => res.json())
    .then(data => {
        showToast(data.message || "Bulk dispatch complete.");
        closeRemediationPanel();
    })
    .catch(() => showToast("Bulk dispatch failed — check network connection."))
    .finally(() => {
        if (bulkBtn) {
            bulkBtn.disabled = false;
            bulkBtn.textContent = "⚡ Bulk Dispatch All";
        }
    });
}

// ==========================================
// PHASE 7: EMAIL TRANSMITTER UI CORE
// ==========================================
function openEmailPanel() {
    const overlay = document.getElementById("email-overlay-panel");
    const targetsList = document.getElementById("email-targets-list");
    const emailInput = document.getElementById("email-recipient-input");
    const editor = document.getElementById("email-content-editor");
    
    if (!overlay) return;
    
    if (emailInput) emailInput.value = "";
    if (editor) editor.value = "";
    window.SELECTED_EMAIL_TARGET_NODE_NAMES = [];

    document.getElementById("email-transmit-btn").disabled = true;
    document.getElementById("ai-email-trigger-btn").disabled = true;
    
    if (targetsList) {
        targetsList.innerHTML = `<p style="color: var(--text-muted); font-size: 0.82rem; text-align: center; margin: 0; padding: 10px;">Loading targets...</p>`;
        
        fetch("/api/suppliers-list")
        .then(res => res.json())
        .then(suppliers => {
            const highRisk = suppliers.filter(s => s.risk_status === "High");
            targetsList.innerHTML = "";
            
            if (highRisk.length === 0) {
                targetsList.innerHTML = `
                    <div class="text-center py-2">
                        <p class="text-success fw-bold" style="font-size:0.82rem; margin:0;">✅ No active high-risk nodes tracked.</p>
                    </div>`;
                return;
            }
            
            highRisk.forEach(node => {
                const nodeItem = document.createElement("div");
                nodeItem.className = "p-2 border rounded cursor-pointer email-target-item mb-1";
                nodeItem.style.cssText = "background: rgba(0,0,0,0.01); border-color: var(--border-color) !important; cursor: pointer; transition: all 0.2s ease;";
                nodeItem.innerHTML = `
                    <div class="form-check d-flex justify-content-between align-items-center w-100 m-0">
                        <div>
                            <input class="form-check-input email-checkbox" type="checkbox" value="${node.contact_email || node.name}" id="chk-em-${node._id}" style="margin-right: 8px; cursor: pointer;">
                            <label class="form-check-label" for="chk-em-${node._id}" style="color: var(--text-primary); font-size:0.82rem; cursor: pointer;">
                                <strong>${node.name}</strong>
                            </label>
                        </div>
                        <span style="font-size:0.75rem; color: var(--text-muted);">${node.contact_email || 'No email'}</span>
                    </div>`;
                nodeItem.onclick = (e) => {
                    const checkbox = document.getElementById(`chk-em-${node._id}`);
                    if (e.target !== checkbox && e.target.tagName !== 'LABEL') {
                        checkbox.checked = !checkbox.checked;
                    }
                    selectEmailTarget(node, checkbox, nodeItem);
                };
                targetsList.appendChild(nodeItem);
            });
        })
        .catch(() => {
            targetsList.innerHTML = `<p style="color: var(--text-muted); font-size: 0.82rem; text-align: center; margin: 0; padding: 10px;">Failed to load targets.</p>`;
        });
    }
    
    overlay.classList.add("is-open");
}

function selectEmailTarget(node, checkbox, element) {
    if (!window.SELECTED_EMAIL_TARGET_NODE_NAMES) {
        window.SELECTED_EMAIL_TARGET_NODE_NAMES = [];
    }
    const index = window.SELECTED_EMAIL_TARGET_NODE_NAMES.indexOf(node.name);
    
    if (checkbox.checked) {
        if (index === -1) window.SELECTED_EMAIL_TARGET_NODE_NAMES.push(node.name);
        element.style.background = "rgba(0, 85, 255, 0.05)";
        element.style.borderColor = "var(--accent-blue) !important";
    } else {
        if (index > -1) window.SELECTED_EMAIL_TARGET_NODE_NAMES.splice(index, 1);
        element.style.background = "rgba(0,0,0,0.01)";
        element.style.borderColor = "var(--border-color) !important";
    }
    
    const emailInput = document.getElementById("email-recipient-input");
    if (emailInput) {
        // Collect all selected emails or fallback to names
        const selectedEmails = [];
        document.querySelectorAll('.email-checkbox:checked').forEach(chk => {
            if (chk.value && chk.value !== 'undefined') selectedEmails.push(chk.value);
        });
        emailInput.value = selectedEmails.join(', ');
        handleRecipientEmailChange();
    }
}

function closeEmailPanel() {
    closeModal("email-overlay-panel");
}

function handleRecipientEmailChange() {
    const emailInput = document.getElementById("email-recipient-input");
    const transmitBtn = document.getElementById("email-transmit-btn");
    const aiBtn = document.getElementById("ai-email-trigger-btn");
    const editor = document.getElementById("email-content-editor");
    
    const email = emailInput.value.trim();
    const isValidEmail = email.length > 0 && email.includes('@') && email.includes('.');
    // AI can be enabled if suppliers are selected OR a valid email is typed
    const hasTargets = (window.SELECTED_EMAIL_TARGET_NODE_NAMES && window.SELECTED_EMAIL_TARGET_NODE_NAMES.length > 0);
    
    transmitBtn.disabled = !(isValidEmail || hasTargets) || !editor.value.trim();
    aiBtn.disabled = !(isValidEmail || hasTargets);
}

function draftEmailWithAI() {
    const emailInput = document.getElementById("email-recipient-input");
    const editor = document.getElementById("email-content-editor");
    const aiBtn = document.getElementById("ai-email-trigger-btn");
    const recipientEmail = emailInput.value.trim();
    
    const hasTargets = window.SELECTED_EMAIL_TARGET_NODE_NAMES && window.SELECTED_EMAIL_TARGET_NODE_NAMES.length > 0;
    if (!hasTargets && !recipientEmail) {
        alert("Please select at least one supplier target or enter a recipient email.");
        return;
    }
    
    aiBtn.disabled = true;
    aiBtn.innerHTML = `⏳ Composing...`;
    
    const targetPayload = hasTargets
        ? window.SELECTED_EMAIL_TARGET_NODE_NAMES.join(',')
        : recipientEmail;
    
    fetch("/api/analytics/draft-ai-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ supplier_name: targetPayload })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            editor.value = data.ai_email_draft;
            handleRecipientEmailChange();
        } else {
            alert("AI Composition Error: " + data.message);
        }
    })
    .catch(() => alert("Network link failed connecting to AI copywriting agents."))
    .finally(() => {
        aiBtn.disabled = false;
        aiBtn.innerHTML = `✨ Compose with AI`;
    });
}

function transmitAlertEmail() {
    const emailInput = document.getElementById("email-recipient-input");
    const editor = document.getElementById("email-content-editor");
    const transmitBtn = document.getElementById("email-transmit-btn");
    
    const recipientEmail = emailInput.value.trim();
    if (!recipientEmail || !editor.value.trim()) return;
    
    transmitBtn.disabled = true;
    transmitBtn.innerHTML = `⏳ Transmitting...`;

    const targetPayload = window.SELECTED_EMAIL_TARGET_NODE_NAMES && window.SELECTED_EMAIL_TARGET_NODE_NAMES.length > 0 
        ? window.SELECTED_EMAIL_TARGET_NODE_NAMES.join(',') 
        : recipientEmail;

    fetch("/api/analytics/send-alert-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
            supplier_name: targetPayload,
            recipient_email: recipientEmail,
            email_body: editor.value
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast(data.message);
            closeEmailPanel();
        } else {
            showToast("Transmission refused: " + data.message);
            transmitBtn.disabled = false;
            transmitBtn.innerHTML = `🚀 Send Alert Email`;
        }
    })
    .catch(() => {
        showToast("SMTP handshake failure — link timeout.");
        transmitBtn.disabled = false;
        transmitBtn.innerHTML = `🚀 Send Alert Email`;
    });
}

// ==========================================
// DASHBOARD STATE RESTORE ON PAGE LOAD
// ==========================================
function initializeDashboardState() {
    const uploadView = document.getElementById("upload-stage-view");
    if (!uploadView) return;

    fetch("/api/suppliers-list")
    .then(res => res.json())
    .then(suppliers => {
        if (!suppliers || suppliers.length === 0) return;

        const isProcessing = suppliers.some(s =>
            s.processing_status === "Pending" || s.processing_status === "Analyzing"
        );

        // If user previously cancelled scanning, or arrived to dashboard to upgrade premium,
        // do not automatically resume polling. Respect persistent cancel state.
        const cancelled = (() => {
            try { return !!localStorage.getItem('scan_cancelled'); } catch (e) { return false; }
        })();
        const isUpgradeIntent = window.location.search.includes("upgrade=premium");

        if (isProcessing && !cancelled && !isUpgradeIntent) {
            uploadView.classList.add("d-none");
            document.getElementById("chef-loading-stage").classList.remove("d-none");
            pollProcessingStatus();
        } else {
            showResultsStage(suppliers);
        }
    })
    .catch(() => {});
}

function showResultsStage(suppliers) {
    const uploadView = document.getElementById("upload-stage-view");
    const loadingView = document.getElementById("chef-loading-stage");
    const resultsView = document.getElementById("results-stage-view");

    if (uploadView) uploadView.classList.add("d-none");
    if (loadingView) loadingView.classList.add("d-none");
    if (resultsView) {
        resultsView.classList.remove("d-none");
        resultsView.classList.add("results-reveal");
    }

    renderSupplierRows(suppliers);
    renderDashboardMetricsCharts();
    if (typeof staggerChartPanels === "function") staggerChartPanels();
    if (typeof staggerTableRows === "function") staggerTableRows();
    showToast("Analysis complete — cockpit data loaded.");
}

// ==========================================
// PHASE 6: UFO-STYLE PLOTLY GRAPH ENGINE
// ==========================================
function getUfoChartTheme() {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const textColor = getComputedStyle(document.documentElement).getPropertyValue("--text-primary").trim();
    const gridColor = isDark ? "rgba(255,255,255,0.06)" : "rgba(0,102,255,0.08)";
    const accentCyan = isDark ? "#FF944D" : "#00F2FF";
    const accentBlue = isDark ? "#FF6600" : "#4DA3FF";

    return {
        textColor,
        gridColor,
        accentCyan,
        accentBlue,
        isDark,
        layout: {
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            margin: { t: 12, b: 36, l: 44, r: 12 },
            font: { color: textColor, family: "Outfit, sans-serif", size: 11 },
            xaxis: { gridcolor: gridColor, zerolinecolor: gridColor, tickfont: { size: 10 } },
            yaxis: { gridcolor: gridColor, zerolinecolor: gridColor, tickfont: { size: 10 } }
        },
        plotConfig: { responsive: true, displayModeBar: false }
    };
}

function renderDashboardMetricsCharts() {
    if (typeof Plotly === "undefined") return;

    fetch("/api/analytics/dashboard-charts")
    .then(res => res.json())
    .then(data => {
        const theme = getUfoChartTheme();

        // 1. Risk Score Bar Chart — clear color-coded risk levels
        const barColors = data.bar_x.map(label => {
            if (label.includes("Critical")) return "#FF4757";
            if (label.includes("Elevated")) return "#FF8C42";
            if (label.includes("Medium")) return "#F59E0B";
            return "#2ECC71";
        });
        Plotly.newPlot("plotly-bar-chart", [{
            x: data.bar_x, y: data.bar_y, type: "bar",
            marker: {
                color: barColors,
                line: { color: theme.isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.05)", width: 1 },
                opacity: 0.92
            },
            text: data.bar_y.map(v => v > 0 ? `${v}` : ""),
            textposition: "outside",
            textfont: { color: theme.textColor, size: 12, family: "Outfit, sans-serif" },
            hovertemplate: "<b>%{x}</b><br>Suppliers: %{y}<extra></extra>"
        }], {
            ...theme.layout,
            bargap: 0.3,
            margin: { t: 24, b: 50, l: 44, r: 12 },
            xaxis: { ...theme.layout.xaxis, tickfont: { size: 9, color: theme.textColor } },
            yaxis: { ...theme.layout.yaxis, range: [0, Math.max(...data.bar_y) + 2], title: { text: "No. of Suppliers", font: { size: 11 } }, dtick: 1 }
        }, theme.plotConfig);

        // 2. Risk Distribution Pie — clean donut with percentages
        const total = data.pie_values.reduce((a, b) => a + b, 0);
        Plotly.newPlot("plotly-pie-chart", [{
            labels: data.pie_labels, values: data.pie_values, type: "pie",
            hole: 0.5,
            marker: {
                colors: ["#2ECC71", "#F59E0B", "#FF4757"],
                line: { color: theme.isDark ? "#1a1a2e" : "#ffffff", width: 2.5 }
            },
            textinfo: "label+percent",
            textposition: "outside",
            textfont: { color: theme.textColor, size: 11, family: "Outfit, sans-serif" },
            hovertemplate: "<b>%{label}</b><br>%{value} supplier(s) · %{percent}<extra></extra>",
            pull: data.pie_values.map((v, i) => data.pie_labels[i].includes("High") ? 0.05 : 0),
            sort: false
        }], {
            ...theme.layout,
            margin: { t: 16, b: 16, l: 16, r: 16 },
            showlegend: false,
            annotations: [{
                text: total > 0 ? `<b>${total}</b><br>Total` : "",
                showarrow: false,
                font: { size: 14, color: theme.textColor, family: "Outfit, sans-serif" },
                x: 0.5, y: 0.5
            }]
        }, theme.plotConfig);

        // 3. Performance vs Risk Heatmap — with cell count annotations
        const heatmapAnnotations = [];
        const xLabels = ["Low Risk", "Medium Risk", "High Risk"];
        const yLabels = ["Strong (≥95%)", "Fair (85-94%)", "Weak (<85%)"];
        for (let i = 0; i < data.heatmap_z.length; i++) {
            for (let j = 0; j < data.heatmap_z[i].length; j++) {
                heatmapAnnotations.push({
                    x: xLabels[j], y: yLabels[i],
                    text: data.heatmap_z[i][j] > 0 ? `${data.heatmap_z[i][j]}` : "—",
                    showarrow: false,
                    font: { color: data.heatmap_z[i][j] > 0 ? "#fff" : (theme.isDark ? "#555" : "#aaa"), size: 14, family: "Outfit" }
                });
            }
        }
        Plotly.newPlot("plotly-heatmap-chart", [{
            z: data.heatmap_z,
            x: xLabels,
            y: yLabels,
            type: "heatmap",
            colorscale: [
                [0, theme.isDark ? "#0f1525" : "#e8f4f8"],
                [0.3, theme.isDark ? "#1a4a3a" : "#a8e6cf"],
                [0.6, theme.isDark ? "#7a4a00" : "#ffd93d"],
                [1, "#FF4757"]
            ],
            showscale: false,
            hovertemplate: "<b>%{y}</b> × <b>%{x}</b><br>Suppliers: %{z}<extra></extra>",
            xgap: 3, ygap: 3
        }], {
            ...theme.layout,
            margin: { t: 12, b: 50, l: 80, r: 12 },
            annotations: heatmapAnnotations,
            xaxis: { ...theme.layout.xaxis, tickfont: { size: 10, color: theme.textColor } },
            yaxis: { ...theme.layout.yaxis, tickfont: { size: 10, color: theme.textColor }, automargin: true }
        }, theme.plotConfig);

        // 4. Certification Expiry Timeline — clear scatter with better labels
        Plotly.newPlot("plotly-timeline-chart", [{
            x: data.timeline_x, y: data.timeline_y,
            type: "scatter", mode: "markers+lines+text",
            marker: {
                size: 12,
                color: theme.accentCyan,
                line: { color: theme.isDark ? "#fff" : "#333", width: 1.5 },
                symbol: "circle"
            },
            line: { width: 2, color: theme.accentBlue, shape: "spline" },
            fill: "tozeroy",
            fillcolor: theme.isDark ? "rgba(255,102,0,0.06)" : "rgba(77,163,255,0.08)",
            hovertemplate: "<b>%{y}</b><br>Projected expiry: %{x}<extra></extra>"
        }], {
            ...theme.layout,
            margin: { t: 12, b: 50, l: 100, r: 20 },
            xaxis: { ...theme.layout.xaxis, title: { text: "Projected Expiry Date", font: { size: 10 } }, tickfont: { size: 9 } },
            yaxis: { ...theme.layout.yaxis, tickfont: { size: 9 }, automargin: true }
        }, theme.plotConfig);

        // 5. Supplier Treemap — cleaner hierarchy visualization
        Plotly.newPlot("plotly-treemap-chart", [{
            type: "treemap",
            labels: data.tree_labels,
            parents: data.tree_parents,
            values: data.tree_values,
            textinfo: "label+value",
            textfont: { family: "Outfit, sans-serif", size: 12 },
            marker: {
                colorscale: theme.isDark
                    ? [[0, "#1A1A2E"], [0.5, "#3a2a00"], [1, "#FF6600"]]
                    : [[0, "#e3f2fd"], [0.5, "#64b5f6"], [1, "#1565c0"]],
                line: { color: theme.isDark ? "#333" : "rgba(255,255,255,0.9)", width: 2 }
            },
            hovertemplate: "<b>%{label}</b><br>Suppliers: %{value}<extra></extra>",
            pathbar: { visible: true, textfont: { size: 10 } }
        }], { ...theme.layout, margin: { t: 4, b: 4, l: 4, r: 4 } }, theme.plotConfig);

        // 6. Supplier Network Graph — clearer nodes and layout
        const nodeCount = data.network_nodes.length;
        const nodeX = data.network_nodes.map((n, i) => i === 0 ? 0 : Math.cos((i / (nodeCount - 1)) * 2 * Math.PI) * 5);
        const nodeY = data.network_nodes.map((n, i) => i === 0 ? 0 : Math.sin((i / (nodeCount - 1)) * 2 * Math.PI) * 5);
        const edgeTrace = {
            x: [], y: [], mode: "lines",
            line: { width: 1.8, color: theme.isDark ? "rgba(255,102,0,0.25)" : "rgba(77,163,255,0.3)" },
            hoverinfo: "none", type: "scatter"
        };

        data.network_edges.forEach(edge => {
            const sIdx = data.network_nodes.findIndex(n => n.id === edge.source);
            const tIdx = data.network_nodes.findIndex(n => n.id === edge.target);
            edgeTrace.x.push(nodeX[sIdx], nodeX[tIdx], null);
            edgeTrace.y.push(nodeY[sIdx], nodeY[tIdx], null);
        });

        const nodeColors = data.network_nodes.map((n, i) => i === 0 ? (theme.isDark ? "#FF6600" : "#1565c0") : theme.accentCyan);
        const nodeSizes = data.network_nodes.map((n, i) => i === 0 ? 22 : 14);

        Plotly.newPlot("plotly-network-chart", [edgeTrace, {
            x: nodeX, y: nodeY,
            mode: "markers+text",
            text: data.network_nodes.map(n => n.label.length > 15 ? n.label.substring(0, 14) + "…" : n.label),
            textposition: "top center",
            textfont: { size: 9, color: theme.textColor, family: "Outfit, sans-serif" },
            marker: {
                size: nodeSizes,
                color: nodeColors,
                line: { color: theme.isDark ? "rgba(255,255,255,0.2)" : "rgba(0,0,0,0.1)", width: 2 },
                opacity: 0.95
            },
            type: "scatter",
            hovertemplate: "<b>%{text}</b><extra></extra>"
        }], {
            ...theme.layout,
            xaxis: { showgrid: false, zeroline: false, showticklabels: false },
            yaxis: { showgrid: false, zeroline: false, showticklabels: false, scaleanchor: "x" },
            margin: { t: 10, b: 10, l: 10, r: 10 }
        }, theme.plotConfig);
    })
    .catch(err => console.error("Chart render failed:", err));
}

// ==========================================
// DRAG & DROP MULTI-FILE FILE HANDLING WORKSPACE
// ==========================================
function initializeDragAndDropUpload() {
    const dropZone = document.getElementById("drop-zone-deck");
    const fileInput = document.getElementById("file-input-hidden");
    const form = document.getElementById("file-drop-form");

    if (!dropZone) return;

    dropZone.addEventListener("click", (e) => {
        if (e.target.tagName !== "BUTTON" && fileInput) fileInput.click();
    });

    ["dragenter", "dragover"].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => { e.preventDefault(); dropZone.classList.add("drag-over"); }, false);
    });

    ["dragleave", "drop"].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => { e.preventDefault(); dropZone.classList.remove("drag-over"); }, false);
    });

    dropZone.addEventListener("drop", (e) => {
        const files = e.dataTransfer.files;
        if (files.length && fileInput) { fileInput.files = files; executeDataCookHandoff(form); }
    });

    if (fileInput) {
        fileInput.addEventListener("change", () => { if (fileInput.files.length) executeDataCookHandoff(form); });
    }
}

function showUploadStage() {
    const uploadStage = document.getElementById("upload-stage-view");
    const loadingStage = document.getElementById("chef-loading-stage");
    const resultsView = document.getElementById("results-stage-view");
    const statusEl = document.getElementById("processing-status-text");

    if (uploadStage) uploadStage.classList.remove("d-none");
    if (loadingStage) loadingStage.classList.add("d-none");
    if (resultsView) resultsView.classList.add("d-none");
    if (statusEl) statusEl.textContent = "Ready for a new upload.";
}

function cancelScanPolling() {
    window.SCAN_CANCELLED = true;
    if (window.SUPPLIER_SCAN_POLL_ID) {
        clearTimeout(window.SUPPLIER_SCAN_POLL_ID);
        window.SUPPLIER_SCAN_POLL_ID = null;
    }
}

function cancelScanAndReset() {
    cancelScanPolling();
    // persist cancellation so navigation doesn't restart polling
    try { localStorage.setItem('scan_cancelled', '1'); } catch (e) {}
    // Tell backend to cancel in-flight processing as well
    fetch('/api/scan-cancel', { method: 'POST' }).catch(() => {});
    showUploadStage();
    const statusEl = document.getElementById("processing-status-text");
    if (statusEl) {
        statusEl.textContent = "Scan canceled. You can upload a new file now.";
    }
    showToast("Scan polling canceled. Backend analysis may still complete, but the client is no longer waiting.");
}


function showLoadingStage() {
    const uploadStage = document.getElementById("upload-stage-view");
    const loadingStage = document.getElementById("chef-loading-stage");
    const resultsView = document.getElementById("results-stage-view");

    if (uploadStage) uploadStage.classList.add("d-none");
    if (loadingStage) loadingStage.classList.remove("d-none");
    if (resultsView) resultsView.classList.add("d-none");
}

function resetUploadStage() {
    showUploadStage();
}

function executeDataCookHandoff(form) {
    showLoadingStage();
    const statusEl = document.getElementById("processing-status-text");
    if (statusEl) statusEl.textContent = "Publishing manifest to the backend and beginning scan...";

    // Clear any previous cancel flag before starting a new upload
    fetch('/api/scan-clear', { method: 'POST' }).catch(() => {});
    try { localStorage.removeItem('scan_cancelled'); } catch (e) {}

    fetch("/api/upload-csv", { method: "POST", body: new FormData(form) })
    .then(response => response.json())
    .then(data => {
        if (data && data.success) {
            showToast(data.message || "Upload received. Scanning dataset...");
            window.SCAN_CANCELLED = false;
            window.SUPPLIER_SCAN_POLL_ID = setTimeout(pollProcessingStatus, 2000);
        } else {
            showToast("Upload failed: " + (data && data.message ? data.message : "Unknown server error."));
            resetUploadStage();
        }
    })
    .catch(() => {
        showToast("Upload connection failure.");
        resetUploadStage();
    });
}

function pollProcessingStatus() {
    fetch("/api/suppliers-list")
    .then(res => res.json())
    .then(suppliers => {
        if (!Array.isArray(suppliers)) {
            showToast("Unexpected server response during dataset scan. Retrying...");
            setTimeout(pollProcessingStatus, 3000);
            return;
        }

        const pending = suppliers.filter(s =>
            s.processing_status === "Pending" || s.processing_status === "Analyzing"
        );
        const statusEl = document.getElementById("processing-status-text");
        if (statusEl) {
            const done = suppliers.length - pending.length;
            statusEl.textContent = suppliers.length === 0
                ? "No supplier records loaded yet. Retrying..."
                : pending.length
                    ? `Analyzing ${pending.length} supplier(s)... (${done}/${suppliers.length} complete)`
                    : "Finalizing cockpit dashboards...";
        }

        if (window.SCAN_CANCELLED) {
            return;
        }

        if (suppliers.length === 0) {
            window.SUPPLIER_SCAN_POLL_ID = setTimeout(pollProcessingStatus, 2000);
            return;
        }

        if (pending.length) {
            showLoadingStage();
            window.SUPPLIER_SCAN_POLL_ID = setTimeout(pollProcessingStatus, 2000);
        } else {
            showResultsStage(suppliers);
        }
    })
    .catch(() => {
        showToast("Upload status check failed. Retrying...");
        setTimeout(pollProcessingStatus, 3000);
    });
}

function renderSupplierRows(suppliers) {
    const tbody = document.getElementById("supplier-table-rows");
    if (!tbody) return;
    tbody.innerHTML = "";

    suppliers.forEach(s => {
        // Hazard badge color based on score
        let hazardBadge = "bg-success";
        if (s.hazard_score > 55) hazardBadge = "bg-danger";
        else if (s.hazard_score > 25) hazardBadge = "bg-warning";

        // Status Rank badge
        let statusColor = "#2ECC71";
        let statusLabel = s.risk_status || "Low";
        if (statusLabel === "High") statusColor = "#FF4757";
        else if (statusLabel === "Medium") statusColor = "#F59E0B";

        const hazardDisplay = s.hazard_score != null ? Math.round(s.hazard_score) : "—";
        const deliveryDisplay = s.overall_on_time_rate != null ? parseFloat(s.overall_on_time_rate).toFixed(1) : "—";

        const row = document.createElement("tr");
        row.className = "clickable-supplier-row";
        row.setAttribute("onclick", `window.location.href='/supplier/${s._id}'`);
        row.innerHTML = `
            <td style="color: var(--text-primary); font-weight: 700;">${s.name}</td>
            <td style="color: var(--text-primary);">${s.category}</td>
            <td style="color: var(--text-primary);">${s.country}</td>
            <td style="color: var(--text-primary);">${deliveryDisplay}%</td>
            <td><span class="badge ${hazardBadge}" style="font-size: 0.78rem; padding: 5px 10px;">${hazardDisplay}/100</span></td>
            <td><span style="display:inline-flex; align-items:center; gap:6px; font-size:0.82rem; font-weight:700; color:${statusColor};"><span style="width:8px;height:8px;border-radius:50%;background:${statusColor};display:inline-block;"></span>${statusLabel}</span></td>`;
        tbody.appendChild(row);
    });
}

// ==========================================
// FUTURISTIC SUPPLIER DETAIL WORKFLOW LOGIC
// ==========================================
function initializeHistoricalTrendsChart() {
    if (!window.HISTORICAL_TIMELINE_DATA || typeof Plotly === "undefined") return;

    const theme = getUfoChartTheme();
    const historyData = window.HISTORICAL_TIMELINE_DATA;
    const months = historyData.map(d => d.month);

    Plotly.newPlot("plotly-trends-frame", [
        { x: months, y: historyData.map(d => d.hazard_score), name: "Hazard Index", type: "scatter", mode: "lines+markers",
            line: { color: "#FF4757", width: 3, shape: "spline" }, marker: { size: 7, symbol: "diamond" } },
        { x: months, y: historyData.map(d => d.on_time_rate), name: "On-Time Performance", type: "scatter", mode: "lines+markers",
            line: { color: theme.accentCyan, width: 3, dash: "dot", shape: "spline" }, marker: { size: 7 } }
    ], {
        ...theme.layout,
        margin: { t: 20, b: 40, l: 44, r: 20 },
        legend: { orientation: "h", y: 1.15, font: { color: theme.textColor, size: 11 } },
        yaxis: { ...theme.layout.yaxis, range: [0, 105] }
    }, theme.plotConfig);
}

function transmitChatQuery(supplierName) {
    const inputField = document.getElementById("chat-input-text");
    const queryText = inputField.value.trim();
    if (!queryText) return;

    const frame = document.getElementById("chat-messages-frame");
    const userBubble = document.createElement("div");
    userBubble.className = "chat-bubble chat-bubble-manager";
    userBubble.textContent = queryText;
    frame.appendChild(userBubble);
    inputField.value = "";
    frame.scrollTop = frame.scrollHeight;

    fetch("/api/chat-compliance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: queryText, supplier_name: supplierName })
    })
    .then(res => res.json())
    .then(data => {
        const aiBubble = document.createElement("div");
        aiBubble.className = "chat-bubble chat-bubble-ai";
        aiBubble.textContent = data.answer;
        frame.appendChild(aiBubble);
        frame.scrollTop = frame.scrollHeight;
    })
    .catch(() => {
        const errorBubble = document.createElement("div");
        errorBubble.className = "chat-bubble chat-bubble-ai text-danger";
        errorBubble.textContent = "System Connection Failure. Link timed out.";
        frame.appendChild(errorBubble);
    });
}

function triggerGitTicketApproval(supplierId) {
    const projectId = prompt("Enter GitLab Project ID:");
    if (!projectId) return;

    const token = prompt("Enter GitLab Access Token (Optional: overrides ENV token):");

    fetch(`/api/approve-gitlab-ticket/${supplierId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, access_token: token })
    })
    .then(res => res.json())
    .then(data => {
        showToast(data.message);
        const banner = document.getElementById("git-approval-banner");
        if (banner) banner.remove();
    })
    .catch(() => showToast("GitLab ticket approval failed."));
}

// ==========================================
// PHASE 8: PREMIUM CHECKOUT OVERLAY ACTIONS
// ==========================================
function toggleWorkspaceCopilot() {
    const bubble = document.getElementById("workspace-copilot-bubble");
    const windowPanel = document.getElementById("workspace-copilot-window");
    if (!windowPanel) return;

    if (windowPanel.classList.contains("d-none")) {
        windowPanel.classList.remove("d-none");
        windowPanel.classList.add("animate-slide-up");
        document.body.style.overflow = "hidden";
    } else {
        windowPanel.classList.add("d-none");
        document.body.style.overflow = "";
    }
}

function sendCopilotQuery() {
    const input = document.getElementById("copilot-input-text");
    const messages = document.getElementById("copilot-chat-messages");
    if (!input || !messages) return;

    const query = input.value.trim();
    if (!query) return;

    const userBubble = document.createElement("div");
    userBubble.className = "chat-bubble chat-bubble-manager";
    userBubble.textContent = query;
    messages.appendChild(userBubble);
    messages.scrollTop = messages.scrollHeight;
    input.value = "";

    fetch("/api/chat-compliance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query })
    })
    .then(res => res.json())
    .then(data => {
        const aiBubble = document.createElement("div");
        aiBubble.className = "chat-bubble chat-bubble-ai";
        aiBubble.textContent = data.answer || "No response received from the AI engine.";
        messages.appendChild(aiBubble);
        messages.scrollTop = messages.scrollHeight;
    })
    .catch(() => {
        const errorBubble = document.createElement("div");
        errorBubble.className = "chat-bubble chat-bubble-ai text-danger";
        errorBubble.textContent = "Connection failed. Please upgrade to Premium or check your network.";
        messages.appendChild(errorBubble);
        messages.scrollTop = messages.scrollHeight;
    });
}

function openPremiumCheckoutPanel() {
    const overlay = document.getElementById("premium-checkout-overlay");
    if (!overlay) {
        window.location.href = "/auth/register";
        return;
    }
    const form = document.getElementById("sandbox-payment-form");
    const spinner = document.getElementById("payment-spinner-overlay");
    if (form) form.classList.remove("d-none");
    if (spinner) spinner.classList.add("d-none");
    overlay.classList.add("is-open");
    document.body.style.overflow = "hidden";
}

function closePremiumCheckoutPanel() {
    closeModal("premium-checkout-overlay");
}

function executeMockPaymentTransition(event) {
    event.preventDefault();
    const form = document.getElementById("sandbox-payment-form");
    const spinner = document.getElementById("payment-spinner-overlay");

    form.classList.add("d-none");
    spinner.classList.remove("d-none");

    setTimeout(() => {
        form.submit();
    }, 1500);
}
// Add these to your script.js
function toggleAISidePanel(targetEditorId) {
    const drawer = document.getElementById('ai-drawer');
    window.activeEditorID = targetEditorId; // Remember which box we are filling
    
    if (drawer) {
        drawer.classList.toggle('ai-drawer-open');
    }
}

async function generateAndInject() {
    const prompt = document.getElementById('ai-prompt-input').value;
    const targetEditor = document.getElementById(window.activeEditorID);
    
    // Call the backend (Example for Email, repeat logic for GitLab if needed)
    fetch("/api/analytics/draft-ai-email", { // Or /api/analytics/draft-ai-ticket
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ supplier_name: window.SELECTED_TARGET_NODE_NAME || "General", prompt: prompt })
    })
    .then(res => res.json())
    .then(data => {
        // Inject the response directly into the textarea that opened the drawer
        if (targetEditor) targetEditor.value = data.ai_email_draft || data.ai_markdown_draft;
        toggleAISidePanel(); // Close drawer after injection
    });
}

// ==========================================
// NEW FEATURES: CLEAR SCAN & RETURN TO UPLOAD
// ==========================================
function clearScanAndReturn() {
    if (!confirm("Clear all current supplier data and return to upload screen?")) return;

    fetch("/api/scan-clear-and-return", { method: "POST" })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast(data.message || "Fleet data cleared.");
            // Clear any persisted cancel state
            try { localStorage.removeItem('scan_cancelled'); } catch (e) {}
            window.SCAN_CANCELLED = false;
            // Reset localStorage for last scan info
            try { localStorage.removeItem('last_scan_filename'); } catch (e) {}
            try { localStorage.removeItem('last_scan_date'); } catch (e) {}
            // Show upload stage
            showUploadStage();
        } else {
            showToast("Error: " + (data.message || "Could not clear data."));
        }
    })
    .catch(() => showToast("Network error while clearing data."));
}

// ==========================================
// NEW FEATURES: SCAN HISTORY
// ==========================================
function toggleScanHistoryPanel() {
    const panel = document.getElementById('scan-history-panel');
    if (!panel) return;
    
    if (panel.classList.contains('d-none')) {
        panel.classList.remove('d-none');
        loadScanHistory();
    } else {
        panel.classList.add('d-none');
    }
}

function saveCurrentScan() {
    const snapshotName = prompt("Enter a name for this scan snapshot:", "Scan " + new Date().toLocaleString());
    if (!snapshotName) return;
    
    fetch("/api/scan-save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: snapshotName })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast(data.message);
        } else {
            showToast("Failed to save: " + data.message);
        }
    })
    .catch(() => showToast("Network error while saving scan."));
}

function loadSavedScan(snapshotId, snapshotName) {
    fetch(`/api/scan-load/${snapshotId}`)
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            // Render the loaded suppliers into the results view
            const suppliers = data.suppliers;
            showResultsStage(suppliers);
            showToast(`Loaded snapshot: ${data.snapshot_name}`);
            closeModal("scan-history-panel");
            document.getElementById("scan-history-panel").classList.add("d-none");
        } else {
            showToast("Failed to load snapshot: " + data.message);
        }
    })
    .catch(() => showToast("Network error loading snapshot."));
}

function deleteSavedScan(snapshotId, event) {
    event.stopPropagation();
    if (!confirm("Delete this saved snapshot?")) return;
    
    fetch(`/api/scan-delete/${snapshotId}`, { method: "DELETE" })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast("Snapshot deleted.");
            loadScanHistory();
        } else {
            showToast("Delete failed: " + data.message);
        }
    })
    .catch(() => showToast("Network error deleting snapshot."));
}

function loadScanHistory() {
    const listEl = document.getElementById('scan-history-list');
    if (!listEl) return;
    
    listEl.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem;">Loading history...</p>';
    
    fetch("/api/scan-history")
    .then(res => res.json())
    .then(data => {
        // Check if response is an array (direct list) or has history property
        const history = Array.isArray(data) ? data : (data.history || []);
        
        if (!history || history.length === 0) {
            listEl.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem;">No scan history found.</p>';
            return;
        }
        
        listEl.innerHTML = '';
        history.forEach(item => {
            const isSaved = item.status === "Saved" && item.snapshot_name;
            const filename = item.snapshot_name || item.filename || 'Unknown scan';
            const date = item.uploaded_at ? new Date(item.uploaded_at).toLocaleString() : 'Unknown date';
            const count = item.supplier_count || 0;
            const status = item.status || 'Completed';
            
            const statusColor = status === 'Saved' ? 'var(--accent-blue)' :
                                status === 'Cleared' ? 'var(--warning-amber)' : 
                                status === 'Processing' ? 'var(--accent-cyan)' : 
                                'var(--success-green)';
            
            const div = document.createElement('div');
            div.className = 'scan-history-item';
            
            // Saved snapshots get a "View" button to restore data + charts
            const actionHtml = isSaved && item._id ? `
                <div class="d-flex gap-1">
                    <button class="btn btn-xs btn-outline-primary" onclick="loadSavedScan('${item._id}', '${escapeHtml(filename).replace(/'/g, "\\'")}')" style="font-size:0.7rem; padding:2px 8px;">👁 View</button>
                </div>
            ` : `<span class="status-badge" style="background: ${statusColor}22; color: ${statusColor}; border: 1px solid ${statusColor}44; font-size:0.65rem;">${status}</span>`;
            
            const icon = isSaved ? '💾' : '📄';
            div.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <div class="filename">${icon} ${escapeHtml(filename.slice(0, 60))}</div>
                        <div class="meta">${date} · ${count} supplier(s)</div>
                    </div>
                    ${actionHtml}
                </div>
            `;
            listEl.appendChild(div);
        });
    })
    .catch(() => {
        listEl.innerHTML = '<p style="color: var(--danger-red); font-size: 0.85rem;">Failed to load scan history.</p>';
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
