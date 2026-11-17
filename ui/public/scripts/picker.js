// Shared page behaviour for the Borrower / Lender / Regulator views:
// the borrower search combobox, status lines, and motion timing helpers.
(function () {
  const $ = (id) => document.getElementById(id);

  function cssMs(name) {
    return parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name)) || 0;
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function setStatus(el, kind, text) {
    if (!kind) { el.className = 'status hidden'; el.textContent = ''; return; }
    const icon = { error: 'ban', info: 'info' }[kind] || 'circle-check';
    el.className = 'status status--' + kind;
    el.innerHTML = Icons.svg(icon, 18);
    const span = document.createElement('span');
    span.textContent = text;
    el.appendChild(span);
  }

  // Markup contract: #borrower-search, #borrower-listbox, #combobox,
  // #selected-display, #selected-name, #selected-did, #clear-selection.
  function BorrowerPicker({ onChange }) {
    const input = $('borrower-search');
    const listbox = $('borrower-listbox');
    const combobox = $('combobox');
    const selectedDisplay = $('selected-display');
    let borrowers = [];
    let items = [];
    let highlighted = -1;
    let selected = null;

    fetch('/api/borrowers')
      .then((r) => r.json())
      .then((data) => { borrowers = data; })
      .catch((err) => console.error('Failed to load borrowers:', err));

    const shortId = (b) => b.id.substring(0, 24) + '...';

    function open(list) {
      items = list;
      highlighted = -1;
      listbox.innerHTML = '';
      list.forEach((b, i) => {
        const opt = document.createElement('div');
        opt.className = 'combobox-option';
        opt.setAttribute('role', 'option');
        opt.id = 'borrower-opt-' + i;
        const label = document.createElement('div');
        label.className = 'combobox-option-label';
        label.textContent = b.label;
        const meta = document.createElement('div');
        meta.className = 'combobox-option-meta';
        meta.textContent = shortId(b);
        opt.append(label, meta);
        opt.addEventListener('mousedown', (e) => { e.preventDefault(); select(b); });
        listbox.appendChild(opt);
      });
      listbox.classList.add('open');
      input.setAttribute('aria-expanded', 'true');
    }

    function close() {
      listbox.classList.remove('open');
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
    }

    function highlight(i) {
      const options = listbox.querySelectorAll('.combobox-option');
      if (!options.length) return;
      highlighted = Math.max(0, Math.min(i, options.length - 1));
      options.forEach((o, j) => o.setAttribute('data-highlighted', j === highlighted));
      options[highlighted].scrollIntoView({ block: 'nearest' });
      input.setAttribute('aria-activedescendant', options[highlighted].id);
    }

    function filter() {
      const q = input.value.toLowerCase();
      return borrowers.filter((b) => b.label.toLowerCase().includes(q) || b.id.toLowerCase().includes(q));
    }

    function select(b) {
      selected = b;
      input.value = '';
      close();
      combobox.classList.add('hidden');
      $('selected-name').textContent = b.label;
      $('selected-did').textContent = shortId(b);
      selectedDisplay.classList.remove('hidden');
      onChange(b);
    }

    function clear() {
      selected = null;
      selectedDisplay.classList.add('hidden');
      combobox.classList.remove('hidden');
      onChange(null);
      input.focus();
    }

    input.addEventListener('focus', () => open(filter()));
    input.addEventListener('click', () => open(filter()));
    input.addEventListener('input', () => open(filter()));
    input.addEventListener('blur', close);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); if (!listbox.classList.contains('open')) open(filter()); highlight(highlighted + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); highlight(highlighted - 1); }
      else if (e.key === 'Enter' && highlighted >= 0 && items[highlighted]) { e.preventDefault(); select(items[highlighted]); }
      else if (e.key === 'Escape') close();
    });
    $('clear-selection').addEventListener('click', clear);

    return { get selected() { return selected; } };
  }

  if (window.location.search.includes('demo=clean')) document.body.classList.add('demo-clean');

  // On the hosted site the backend runs on the author's PC; say so when it is unreachable.
  function showOffline() {
    const wrapper = document.querySelector('.page-wrapper');
    if (!wrapper || document.querySelector('.offline-banner')) return;
    const banner = document.createElement('div');
    banner.className = 'offline-banner';
    banner.setAttribute('role', 'status');
    banner.innerHTML = Icons.svg('info', 18) + '<span>The live backend is offline. The ledger and proof server run on the author\'s machine and are switched on for scheduled demos.</span>';
    wrapper.prepend(banner);
  }
  const ctrl = new AbortController();
  setTimeout(() => ctrl.abort(), 8000);
  fetch('/api/health', { signal: ctrl.signal })
    .then((r) => r.json())
    .then((h) => { if (!h.ok) showOffline(); })
    .catch(showOffline);

  window.Demo = { $, cssMs, sleep, setStatus, BorrowerPicker };
})();
