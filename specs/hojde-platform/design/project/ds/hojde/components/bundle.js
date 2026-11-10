/* @ds-bundle: {"format":4,"namespace":"Hojde","components":[{"name":"Button"},{"name":"Badge"},{"name":"Input"},{"name":"ServiceCard"},{"name":"Stat"}]} */
(function () {
  var R = window.React, h = R.createElement;
  function cx() { return Array.prototype.filter.call(arguments, Boolean).join(' '); }
  function omit(o, keys) { var r = {}; for (var k in o) if (keys.indexOf(k) < 0) r[k] = o[k]; return r; }

  function Button(p) {
    var variant = p.variant || 'secondary', size = p.size || 'md';
    var rest = omit(p, ['variant', 'size', 'className', 'children', 'href']);
    rest.className = cx('hj-btn', variant !== 'secondary' && 'hj-btn-' + variant, size === 'sm' && 'hj-btn-sm', p.className);
    if (p.href) { rest.href = p.href; return h('a', rest, p.children); }
    if (!rest.type) rest.type = 'button';
    return h('button', rest, p.children);
  }

  function Badge(p) {
    var tone = p.tone || 'neutral';
    return h('span', { className: cx('hj-badge', tone !== 'neutral' && 'hj-badge-' + tone, p.className) },
      p.dot ? h('span', { className: 'hj-dot', 'aria-hidden': 'true' }) : null, p.children);
  }

  var uid = 0;
  function Input(p) {
    var idRef = R.useRef(null);
    if (!idRef.current) idRef.current = p.id || 'hj-in-' + (++uid);
    var id = idRef.current, hintId = id + '-hint';
    var rest = omit(p, ['label', 'hint', 'error', 'className', 'id']);
    rest.id = id; rest.className = 'hj-input';
    if (p.error) rest['aria-invalid'] = 'true';
    if (p.hint || p.error) rest['aria-describedby'] = hintId;
    return h('div', { className: cx('hj-field', p.className) },
      p.label ? h('label', { htmlFor: id }, p.label) : null,
      h('input', rest),
      p.error ? h('span', { id: hintId, className: 'hj-error' }, p.error)
        : p.hint ? h('span', { id: hintId, className: 'hj-hint' }, p.hint) : null);
  }

  var LINE_TONE = { drone: 'signal', data: 'kote', ai: 'kote' };
  var LINE_LABEL = { drone: 'Droneydelse', data: 'Dataanalyse', ai: 'AI-ydelse' };
  function ServiceCard(p) {
    var line = p.line || 'drone';
    return h('article', { className: cx('hj-card', p.className) },
      h('div', null, h(Badge, { tone: LINE_TONE[line] || 'neutral' }, p.eyebrow || LINE_LABEL[line])),
      h('h3', { className: 'hj-card-title' }, p.title),
      p.description ? h('p', { className: 'hj-card-desc' }, p.description) : null,
      p.specs && p.specs.length ? h('ul', { className: 'hj-card-specs' }, p.specs.map(function (s, i) { return h('li', { key: i }, s); })) : null,
      (p.price || p.cta) ? h('div', { className: 'hj-card-foot' },
        p.price ? h('span', { className: 'hj-price' }, p.price, p.priceNote ? h('small', null, ' ' + p.priceNote) : null) : h('span'),
        p.cta ? h(Button, { variant: p.featured ? 'primary' : 'secondary', size: 'sm', href: p.href, onClick: p.onCta }, p.cta) : null) : null);
  }

  function Stat(p) {
    var trend = p.trend || 'flat';
    return h('div', { className: cx('hj-stat', p.className) },
      h('span', { className: 'hj-stat-label' }, p.label),
      h('span', { className: 'hj-stat-value' }, p.value, p.unit ? h('span', { className: 'hj-stat-unit' }, p.unit) : null),
      p.delta ? h('span', { className: cx('hj-stat-delta', trend !== 'flat' && 'hj-stat-delta-' + trend) },
        (trend === 'up' ? '\u25B2 ' : trend === 'down' ? '\u25BC ' : '\u2013 ') + p.delta) : null);
  }

  window.Hojde = Object.assign(window.Hojde || {}, { Button: Button, Badge: Badge, Input: Input, ServiceCard: ServiceCard, Stat: Stat });
})();
