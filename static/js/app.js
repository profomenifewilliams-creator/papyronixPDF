(function () {
  'use strict';

  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  document.addEventListener('DOMContentLoaded', () => {
    const search = document.getElementById('toolSearch');
    const cards = Array.from(document.querySelectorAll('.searchable-tool'));
    const noResults = document.getElementById('noToolResults');
    if (search) {
      search.addEventListener('input', () => {
        const value = search.value.trim().toLowerCase();
        let visible = 0;
        cards.forEach((card) => {
          const match = (card.dataset.search || card.textContent).toLowerCase().includes(value);
          card.classList.toggle('d-none', !match);
          if (match) visible += 1;
        });
        if (noResults) noResults.classList.toggle('d-none', visible > 0);
      });
    }

    document.querySelectorAll('[data-confirm]').forEach((form) => {
      form.addEventListener('submit', (event) => {
        const prompt = form.getAttribute('data-confirm') || 'Continue?';
        if (!window.confirm(prompt)) event.preventDefault();
      });
    });

    document.querySelectorAll('[data-fill-question]').forEach((button) => {
      button.addEventListener('click', () => {
        const textarea = document.getElementById('question');
        if (!textarea) return;
        textarea.value = button.getAttribute('data-fill-question') || '';
        textarea.focus();
      });
    });

    const splitMode = document.getElementById('splitMode');
    const rangeOptions = document.getElementById('rangeOptions');
    const fixedOptions = document.getElementById('fixedOptions');
    const syncSplitMode = () => {
      if (!splitMode) return;
      const fixed = splitMode.value === 'fixed';
      const each = splitMode.value === 'each';
      if (rangeOptions) rangeOptions.classList.toggle('d-none', fixed || each);
      if (fixedOptions) fixedOptions.classList.toggle('d-none', !fixed);
    };
    if (splitMode) {
      splitMode.addEventListener('change', syncSplitMode);
      syncSplitMode();
    }

    const fileInput = document.getElementById('pdfFileInput');
    const dropZone = document.getElementById('fileDropZone');
    const selectedFiles = document.getElementById('selectedFiles');
    const toolForm = document.getElementById('pdfToolForm');
    let fileState = [];

    const syncFileInput = () => {
      if (!fileInput || typeof DataTransfer === 'undefined') return;
      try {
        const transfer = new DataTransfer();
        fileState.forEach((file) => transfer.items.add(file));
        fileInput.files = transfer.files;
      } catch (_) {
        // Browsers that reject FileList reassignment still support selecting files normally.
      }
    };

    const renderSelectedFiles = () => {
      if (!selectedFiles) return;
      selectedFiles.replaceChildren();
      if (!fileState.length) return;
      const caption = document.createElement('div');
      caption.className = 'file-count-label';
      caption.textContent = `${fileState.length} file${fileState.length === 1 ? '' : 's'} selected`;
      selectedFiles.appendChild(caption);
      fileState.forEach((file, index) => {
        const row = document.createElement('div');
        row.className = 'selected-file-row';
        const badge = document.createElement('span');
        badge.className = 'selected-file-badge';
        badge.textContent = (file.name.split('.').pop() || 'FILE').slice(0, 5).toUpperCase();
        const meta = document.createElement('span');
        meta.className = 'selected-file-meta';
        const name = document.createElement('b');
        name.textContent = file.name;
        const size = document.createElement('small');
        size.textContent = formatSize(file.size);
        meta.append(name, size);
        row.append(badge, meta);
        if (fileInput && fileInput.multiple) {
          const order = document.createElement('span');
          order.className = 'file-order-controls';
          const up = document.createElement('button');
          up.type = 'button'; up.textContent = '↑'; up.setAttribute('aria-label', `Move ${file.name} up`); up.disabled = index === 0;
          up.addEventListener('click', () => { [fileState[index - 1], fileState[index]] = [fileState[index], fileState[index - 1]]; syncFileInput(); renderSelectedFiles(); });
          const down = document.createElement('button');
          down.type = 'button'; down.textContent = '↓'; down.setAttribute('aria-label', `Move ${file.name} down`); down.disabled = index === fileState.length - 1;
          down.addEventListener('click', () => { [fileState[index + 1], fileState[index]] = [fileState[index], fileState[index + 1]]; syncFileInput(); renderSelectedFiles(); });
          order.append(up, down); row.appendChild(order);
        }
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'remove-selected-file'; remove.textContent = '×';
        remove.setAttribute('aria-label', `Remove ${file.name}`);
        remove.addEventListener('click', () => { fileState = fileState.filter((_, fileIndex) => fileIndex !== index); syncFileInput(); renderSelectedFiles(); });
        row.appendChild(remove);
        selectedFiles.appendChild(row);
      });
    };

    const addFiles = (fileList) => {
      const incoming = Array.from(fileList || []);
      if (!fileInput) return;
      const allowed = (fileInput.accept || '').split(',').map((x) => x.trim().toLowerCase()).filter(Boolean);
      const valid = incoming.filter((file) => {
        const name = file.name.toLowerCase();
        return allowed.some((ext) => ext.startsWith('.') ? name.endsWith(ext) : file.type === ext);
      });
      const invalid = incoming.length - valid.length;
      if (invalid) window.alert(`Skipped ${invalid} file${invalid === 1 ? '' : 's'} with unsupported file types.`);
      const combined = fileState.concat(valid);
      const deduped = [];
      const keys = new Set();
      combined.forEach((file) => {
        const key = `${file.name}:${file.size}:${file.lastModified}`;
        if (!keys.has(key)) { keys.add(key); deduped.push(file); }
      });
      fileState = fileInput.multiple ? deduped : deduped.slice(-1);
      syncFileInput();
      renderSelectedFiles();
    };

    if (fileInput) {
      fileInput.addEventListener('change', () => {
        const picked = Array.from(fileInput.files || []);
        fileState = picked;
        renderSelectedFiles();
      });
    }
    if (dropZone && fileInput) {
      ['dragenter', 'dragover'].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.add('is-dragging'); }));
      ['dragleave', 'drop'].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.remove('is-dragging'); }));
      dropZone.addEventListener('drop', (event) => { if (event.dataTransfer && event.dataTransfer.files.length) addFiles(event.dataTransfer.files); });
      dropZone.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); fileInput.click(); } });
      // Clicking anywhere on the label opens the native file picker.
    }

    const showError = (message) => {
      const target = document.getElementById('liveError');
      const success = document.getElementById('liveSuccess');
      if (!target) { window.alert(message); return; }
      target.textContent = message;
      target.classList.remove('d-none');
      if (success) success.classList.add('d-none');
    };
    const showSuccess = (message) => {
      const target = document.getElementById('liveSuccess');
      const error = document.getElementById('liveError');
      if (target) { target.textContent = message; target.classList.remove('d-none'); }
      if (error) error.classList.add('d-none');
    };

    if (toolForm) {
      toolForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const liveError = document.getElementById('liveError');
        const liveSuccess = document.getElementById('liveSuccess');
        const button = document.getElementById('processButton');
        const buttonLabel = button && button.querySelector('.button-label');
        const buttonLoading = button && button.querySelector('.button-loading');
        if (!fileInput || !fileInput.files || !fileInput.files.length) { showError('Choose a file before processing.'); return; }
        if (button) button.disabled = true;
        if (buttonLabel) buttonLabel.classList.add('d-none');
        if (buttonLoading) buttonLoading.classList.remove('d-none');
        if (liveError) liveError.classList.add('d-none');
        if (liveSuccess) liveSuccess.classList.add('d-none');
        try {
          const response = await fetch(toolForm.action, { method: 'POST', body: new FormData(toolForm), credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
          const disposition = response.headers.get('Content-Disposition') || '';
          if (response.ok && disposition.toLowerCase().includes('attachment')) {
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            const nameMatch = disposition.match(/filename="?([^";]+)"?/i);
            anchor.href = url;
            anchor.download = nameMatch ? nameMatch[1] : 'papyronix-output';
            document.body.appendChild(anchor); anchor.click(); anchor.remove();
            window.setTimeout(() => URL.revokeObjectURL(url), 2500);
            showSuccess('Processing completed. Your download has started. Your original file was not changed.');
          } else {
            const html = await response.text();
            const parsed = new DOMParser().parseFromString(html, 'text/html');
            const message = parsed.querySelector('.tool-error span')?.textContent?.trim() || parsed.querySelector('.tool-error')?.textContent?.trim() || `Processing could not be completed (HTTP ${response.status}).`;
            showError(message);
          }
        } catch (_) {
          showError('The local server could not be reached. Make sure Django is running and try again.');
        } finally {
          if (button) button.disabled = false;
          if (buttonLabel) buttonLabel.classList.remove('d-none');
          if (buttonLoading) buttonLoading.classList.add('d-none');
        }
      });
    }
  });
})();
