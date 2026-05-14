function buildOverlay(title, steps) {
    let overlay = document.getElementById('process-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'process-overlay';
        overlay.className = 'process-overlay';
        overlay.innerHTML = `
            <div class="process-overlay-card">
                <div class="process-overlay-header" id="process-overlay-title"></div>
                <div class="process-overlay-body">
                    <div class="upload-progress-panel" id="upload-progress-panel" style="display:none;">
                        <div class="label-row">
                            <span>Upload Transfer</span>
                            <strong id="upload-progress-percent">0%</strong>
                        </div>
                        <div class="label-row small-row">
                            <span id="upload-progress-speed">Speed: 0 KB/s</span>
                            <span id="upload-progress-eta">ETA: --</span>
                        </div>
                        <div class="progress">
                            <div
                                id="upload-progress-bar"
                                class="progress-bar bg-success"
                                role="progressbar"
                                style="width: 0%;"
                                aria-valuemin="0"
                                aria-valuemax="100"
                                aria-valuenow="0"
                            ></div>
                        </div>
                    </div>
                    <ol class="trace-list" id="process-overlay-steps"></ol>
                    <div class="overlay-actions">
                        <button type="button" class="btn btn-primary" id="overlay-close-btn" style="display:none;">Close</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
    }

    const titleNode = document.getElementById('process-overlay-title');
    const stepList = document.getElementById('process-overlay-steps');
    titleNode.textContent = title;
    stepList.innerHTML = '';

    steps.forEach((step) => {
        const li = document.createElement('li');
        li.className = 'trace-list-item pending';
        li.innerHTML = `<div class="trace-title">${step}</div><div class="trace-detail">Waiting to execute...</div>`;
        stepList.appendChild(li);
    });

    return overlay;
}

function setUploadProgress(percent, visible) {
    const panel = document.getElementById('upload-progress-panel');
    const bar = document.getElementById('upload-progress-bar');
    const label = document.getElementById('upload-progress-percent');
    const speedLabel = document.getElementById('upload-progress-speed');
    const etaLabel = document.getElementById('upload-progress-eta');

    if (!panel || !bar || !label || !speedLabel || !etaLabel) {
        return;
    }

    panel.style.display = visible ? 'block' : 'none';
    const bounded = Math.max(0, Math.min(100, percent));
    bar.style.width = `${bounded}%`;
    bar.setAttribute('aria-valuenow', String(bounded));
    label.textContent = `${bounded}%`;

    if (!visible) {
        speedLabel.textContent = 'Speed: 0 KB/s';
        etaLabel.textContent = 'ETA: --';
    }
}

function formatTransferRate(bytesPerSecond) {
    if (bytesPerSecond < 1024) {
        return `${Math.max(0, Math.round(bytesPerSecond))} B/s`;
    }
    if (bytesPerSecond < 1024 * 1024) {
        return `${(bytesPerSecond / 1024).toFixed(1)} KB/s`;
    }
    return `${(bytesPerSecond / (1024 * 1024)).toFixed(2)} MB/s`;
}

function formatEta(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) {
        return '--';
    }
    if (seconds < 60) {
        return `${Math.max(1, Math.round(seconds))}s`;
    }
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}m ${secs}s`;
}

function submitWithUploadProgress(form, submitBtn, title, steps) {
    const overlay = buildOverlay(title, steps);
    overlay.classList.add('show');
    setUploadProgress(0, true);

    const stepItems = Array.from(document.querySelectorAll('#process-overlay-steps .trace-list-item'));
    const animationTimer = animateSteps(stepItems, 700);
    const closeBtn = document.getElementById('overlay-close-btn');
    if (closeBtn) {
        closeBtn.style.display = 'none';
        closeBtn.textContent = 'Close';
        closeBtn.onclick = null;
    }

    const xhr = new XMLHttpRequest();
    xhr.open(form.method || 'POST', form.action, true);
    const speedLabel = document.getElementById('upload-progress-speed');
    const etaLabel = document.getElementById('upload-progress-eta');
    const startedAt = performance.now();

    xhr.upload.onprogress = function(event) {
        if (!event.lengthComputable) {
            return;
        }
        const percent = Math.round((event.loaded / event.total) * 100);
        setUploadProgress(percent, true);

        const elapsedSec = (performance.now() - startedAt) / 1000;
        if (elapsedSec <= 0) {
            return;
        }

        const bytesPerSec = event.loaded / elapsedSec;
        const remainingBytes = Math.max(0, event.total - event.loaded);
        const etaSec = bytesPerSec > 0 ? remainingBytes / bytesPerSec : Number.POSITIVE_INFINITY;

        if (speedLabel) {
            speedLabel.textContent = `Speed: ${formatTransferRate(bytesPerSec)}`;
        }
        if (etaLabel) {
            etaLabel.textContent = `ETA: ${formatEta(etaSec)}`;
        }
    };

    xhr.onload = function() {
        clearInterval(animationTimer);
        stepItems.forEach((item) => {
            item.classList.remove('pending');
            item.classList.remove('active');
            item.classList.add('completed');
            const detail = item.querySelector('.trace-detail');
            if (detail) {
                detail.textContent = 'Completed';
            }
        });

        setUploadProgress(100, true);
        if (speedLabel) {
            speedLabel.textContent = 'Speed: Completed';
        }
        if (etaLabel) {
            etaLabel.textContent = 'ETA: 0s';
        }

        if (xhr.status >= 200 && xhr.status < 400) {
            if (closeBtn) {
                closeBtn.textContent = 'Close & Continue';
                closeBtn.style.display = 'inline-block';
                closeBtn.onclick = () => {
                    overlay.classList.remove('show');
                    setUploadProgress(0, false);
                    window.location.href = xhr.responseURL || form.action;
                };
            } else {
                window.location.href = xhr.responseURL || form.action;
            }
            return;
        }

        if (closeBtn) {
            closeBtn.textContent = 'Close';
            closeBtn.style.display = 'inline-block';
            closeBtn.onclick = () => {
                overlay.classList.remove('show');
                setUploadProgress(0, false);
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Upload & Encrypt';
                }
                window.location.reload();
            };
        } else {
            overlay.classList.remove('show');
            setUploadProgress(0, false);
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Upload & Encrypt';
            }
            window.location.reload();
        }
    };

    xhr.onerror = function() {
        clearInterval(animationTimer);
        if (closeBtn) {
            closeBtn.textContent = 'Close';
            closeBtn.style.display = 'inline-block';
            closeBtn.onclick = () => {
                overlay.classList.remove('show');
                setUploadProgress(0, false);
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Upload & Encrypt';
                }
            };
        }
        alert('Upload failed during transfer. Please try again.');
    };

    const formData = new FormData(form);
    xhr.send(formData);
}

function animateSteps(stepItems, intervalMs) {
    let index = 0;
    return setInterval(() => {
        if (stepItems.length === 0) {
            return;
        }

        if (index > 0 && index - 1 < stepItems.length) {
            stepItems[index - 1].classList.remove('active');
            stepItems[index - 1].classList.add('completed');
            const detail = stepItems[index - 1].querySelector('.trace-detail');
            if (detail) {
                detail.textContent = 'Completed';
            }
        }

        if (index < stepItems.length) {
            stepItems[index].classList.remove('pending');
            stepItems[index].classList.add('active');
            const detail = stepItems[index].querySelector('.trace-detail');
            if (detail) {
                detail.textContent = 'Executing...';
            }
            index += 1;
            return;
        }

        if (stepItems.length > 0) {
            stepItems[stepItems.length - 1].classList.remove('active');
            stepItems[stepItems.length - 1].classList.add('completed');
        }
    }, intervalMs);
}

document.addEventListener('DOMContentLoaded', function() {
    const forms = document.querySelectorAll('form');
    forms.forEach((form) => {
        form.addEventListener('submit', function() {
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Processing...';
            }
        });
    });

    const traceForms = document.querySelectorAll('.trace-form');
    traceForms.forEach((form) => {
        form.addEventListener('submit', function(event) {
            const title = this.dataset.traceTitle || 'Secure Processing';
            let steps = [];
            try {
                steps = JSON.parse(this.dataset.traceSteps || '[]');
            } catch (_error) {
                steps = ['Processing request'];
            }

            const submitBtn = this.querySelector('button[type="submit"]');
            const uploadProgressEnabled = this.dataset.enableUploadProgress === 'true';
            if (uploadProgressEnabled) {
                event.preventDefault();
                submitWithUploadProgress(this, submitBtn, title, steps);
                return;
            }

            const overlay = buildOverlay(title, steps);
            overlay.classList.add('show');
            setUploadProgress(0, false);
            const stepItems = Array.from(document.querySelectorAll('#process-overlay-steps .trace-list-item'));
            animateSteps(stepItems, 700);
        });
    });

    const downloadTraceRoot = document.getElementById('download-flow-trace');
    const startDownloadBtn = document.getElementById('start-download-btn');
    if (downloadTraceRoot && startDownloadBtn) {
        const items = Array.from(document.querySelectorAll('#download-trace-list .trace-list-item'));
        let running = false;

        startDownloadBtn.addEventListener('click', function() {
            if (running) {
                return;
            }

            running = true;
            startDownloadBtn.disabled = true;
            startDownloadBtn.textContent = 'Executing secure pipeline...';

            let i = 0;
            const timer = setInterval(() => {
                if (i > 0) {
                    items[i - 1].classList.remove('active');
                    items[i - 1].classList.add('completed');
                }

                if (i < items.length) {
                    items[i].classList.remove('pending');
                    items[i].classList.add('active');
                    i += 1;
                    return;
                }

                clearInterval(timer);
                startDownloadBtn.textContent = 'Starting file transfer...';
                window.location.href = startDownloadBtn.dataset.fileUrl;
            }, 850);
        });
    }

    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});