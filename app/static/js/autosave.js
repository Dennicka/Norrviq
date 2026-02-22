(function () {
  const forms = document.querySelectorAll('[data-autosave="true"]');
  const DEBOUNCE_MS = 1000;

  function setStatus(form, text, kind) {
    const node = form.querySelector('[data-autosave-status]');
    if (!node) return;
    node.textContent = text;
    node.dataset.statusKind = kind || '';
  }

  function storageKey(form) {
    return `draft:${form.dataset.autosaveEntity}:${form.dataset.autosaveId}:${form.dataset.autosaveFieldhash || 'default'}`;
  }

  function collect(form) {
    const data = {};
    Array.from(form.querySelectorAll('[data-autosave-field="true"], input[name], select[name], textarea[name]')).forEach((el) => {
      if (el.name === 'csrf_token' || el.type === 'hidden') return;
      if (!el.name) return;
      if (el.type === 'checkbox') data[el.name] = !!el.checked;
      else data[el.name] = el.value;
    });
    return data;
  }

  function renderErrors(form, fields, fallback) {
    form.querySelectorAll('.autosave-field-error').forEach((n) => n.remove());
    Array.from(form.querySelectorAll('[data-autosave-field="true"], input[name], select[name], textarea[name]')).forEach((el) => el.classList.remove('autosave-error'));
    const top = form.querySelector('[data-autosave-form-error]');
    if (top) top.textContent = fallback || '';

    Object.entries(fields || {}).forEach(([field, message]) => {
      const input = form.querySelector(`[name="${field}"]`);
      if (!input) return;
      input.classList.add('autosave-error');
      const err = document.createElement('div');
      err.className = 'autosave-field-error';
      err.textContent = message;
      input.insertAdjacentElement('afterend', err);
    });
  }

  async function save(form) {
    const payload = collect(form);
    const key = storageKey(form);
    const draft = { ts: Date.now(), payload };
    localStorage.setItem(key, JSON.stringify(draft));

    const endpoint = form.dataset.autosaveEndpoint;
    if (!endpoint) {
      setStatus(form, 'Saved locally', 'offline');
      return;
    }

    setStatus(form, 'Saving…', 'saving');
    renderErrors(form, {}, '');
    try {
      const res = await window.appFetch(endpoint, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        if (data && data.error === 'validation') {
          renderErrors(form, data.fields || {}, 'Validation error');
          setStatus(form, `Error: validation`, 'error');
          return;
        }
        setStatus(form, `Error: ${data.error || 'request failed'}`, 'error');
        return;
      }
      if (data.updated_at) form.dataset.serverUpdatedAt = data.updated_at;
      localStorage.removeItem(key);
      setStatus(form, 'Saved', 'saved');
    } catch (e) {
      setStatus(form, 'Offline / retrying…', 'offline');
    }
  }

  forms.forEach((form) => {
    const key = storageKey(form);
    const restoreWrap = form.querySelector('[data-autosave-restore]');
    const draftRaw = localStorage.getItem(key);
    if (draftRaw && restoreWrap) {
      try {
        const draft = JSON.parse(draftRaw);
        const serverTs = Date.parse(form.dataset.serverUpdatedAt || 0) || 0;
        if (draft.ts > serverTs) {
          restoreWrap.hidden = false;
          restoreWrap.querySelector('[data-restore]').addEventListener('click', () => {
            Object.entries(draft.payload || {}).forEach(([name, value]) => {
              const el = form.querySelector(`[name="${name}"]`);
              if (!el) return;
              if (el.type === 'checkbox') el.checked = !!value;
              else el.value = value;
            });
            setStatus(form, 'Draft restored', 'saved');
            restoreWrap.hidden = true;
          });
          restoreWrap.querySelector('[data-discard]').addEventListener('click', () => {
            localStorage.removeItem(key);
            restoreWrap.hidden = true;
          });
        }
      } catch (_) {}
    }

    let timer = null;
    Array.from(form.querySelectorAll('[data-autosave-field="true"], input[name], select[name], textarea[name]')).forEach((el) => {
      if (el.name === 'csrf_token' || el.type === 'hidden') return;
      const eventName = el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input';
      el.addEventListener(eventName, () => {
        clearTimeout(timer);
        timer = setTimeout(() => save(form), DEBOUNCE_MS);
      });
    });
  });
})();
