// Rede da Ejota: áreas fixas numa linha (Marketing no centro) e projetos
// posicionados por forças entre as áreas a que se ligam. Sem bibliotecas.
(function () {
  "use strict";
  var dados = JSON.parse(document.getElementById("dados-rede").textContent);
  var svg = document.getElementById("rede");
  var painel = document.getElementById("painel");
  var NS = "http://www.w3.org/2000/svg";
  var ESP = 130, ALT = 540, MEIO = ALT / 2;
  var LARG = Math.max(700, dados.areas.length * ESP + 120);
  svg.setAttribute("viewBox", "0 0 " + LARG + " " + ALT);

  var areas = {};
  dados.areas.forEach(function (a, i) {
    a.x = 60 + ESP / 2 + i * ESP + (LARG - 120 - dados.areas.length * ESP) / 2;
    a.y = MEIO;
    a.r = a.central ? 46 : 36;
    areas[a.id] = a;
  });

  var porArea = {};
  var projetos = dados.projetos.map(function (p) {
    var principal = areas[p.areas[0]];
    var n = (porArea[principal.id] = (porArea[principal.id] || 0) + 1);
    var soma = 0, peso = 0;
    p.areas.forEach(function (id, k) { var w = k === 0 ? 2 : 1; soma += areas[id].x * w; peso += w; });
    var lado = n % 2 ? -1 : 1;
    return Object.assign(p, {
      x: soma / peso + ((n % 3) - 1) * 30,
      y: MEIO + lado * (120 + Math.floor((n - 1) / 2) * 50),
      r: 9 + Math.min(9, Math.sqrt(p.valor || 0) / 14)
    });
  });

  // Relaxamento determinístico: molas até as áreas, repulsão entre os nós.
  for (var it = 0; it < 500; it++) {
    projetos.forEach(function (p) {
      var fx = 0, fy = 0;
      p.areas.forEach(function (id, k) {
        var a = areas[id], dx = a.x - p.x, dy = a.y - p.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
        var alvo = k === 0 ? 135 : 175, f = (d - alvo) * (k === 0 ? 0.05 : 0.03);
        fx += f * dx / d; fy += f * dy / d;
      });
      projetos.forEach(function (q) {
        if (q === p) return;
        var dx = p.x - q.x, dy = p.y - q.y, d = Math.sqrt(dx * dx + dy * dy) || 0.1, min = p.r + q.r + 30;
        if (d < min * 2) { var f = (min * 2 - d) * 0.06; fx += f * dx / d; fy += f * dy / d; }
      });
      dados.areas.forEach(function (a) {
        var dx = p.x - a.x, dy = p.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 0.1, min = a.r + p.r + 28;
        if (d < min) { var f = (min - d) * 0.3; fx += f * dx / d; fy += f * dy / d; }
      });
      // projetos não cruzam a linha das áreas: cada um fica do seu lado
      if (Math.abs(p.y - MEIO) < 70) fy += (p.y < MEIO ? -1 : 1) * 3;
      p.x = Math.max(20, Math.min(LARG - 20, p.x + Math.max(-8, Math.min(8, fx))));
      p.y = Math.max(24, Math.min(ALT - 24, p.y + Math.max(-8, Math.min(8, fy))));
    });
  }

  var sel = null;

  function el(tag, attrs, pai) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    (pai || svg).appendChild(e);
    return e;
  }

  function desenhar() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var ligados = {};
    if (sel) {
      ligados[sel.id] = 1;
      if (sel.areas) sel.areas.forEach(function (id) { ligados[id] = 1; });
      else projetos.forEach(function (p) { if (p.areas.indexOf(sel.id) >= 0) ligados[p.id] = 1; });
    }
    var apagar = function (id) { return sel && !ligados[id] ? " apagado" : ""; };
    for (var i = 1; i < dados.areas.length; i++) {
      var a = dados.areas[i - 1], b = dados.areas[i];
      el("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, "class": "espinha" + (sel ? " apagado" : "") });
    }
    projetos.forEach(function (p) {
      p.areas.forEach(function (id, k) {
        var a = areas[id], ativa = sel && (sel === p || sel === a);
        el("line", { x1: p.x, y1: p.y, x2: a.x, y2: a.y,
          "class": (ativa ? "ativa" : k === 0 ? "principal" : "") + (sel && !ativa ? " apagado" : "") });
      });
    });
    dados.areas.forEach(function (a) {
      var c = el("circle", { cx: a.x, cy: a.y, r: a.r, "class": "area" + apagar(a.id) });
      c.addEventListener("click", function () { selecionar(a); });
      el("title", {}, c).textContent = a.rotulo;
      var t = el("text", { x: a.x, y: a.y + 1, "text-anchor": "middle", "class": "t-area" + apagar(a.id) });
      t.textContent = a.rotulo;
      var n = el("text", { x: a.x, y: a.y + 16, "text-anchor": "middle", "class": "t-area" + apagar(a.id), "font-size": 10, style: "font-weight:400;font-size:10px" });
      n.textContent = a.projetos + " projeto(s)";
    });
    projetos.forEach(function (p) {
      var c = el("circle", { cx: p.x, cy: p.y, r: p.r, "class": "proj p-" + p.saude + (sel === p ? " sel" : "") + apagar(p.id), tabindex: 0 });
      c.addEventListener("click", function () { selecionar(p); });
      c.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); selecionar(p); } });
      el("title", {}, c).textContent = p.rotulo + " · " + p.cliente;
      var t = el("text", { x: p.x, y: p.y + p.r + 12, "text-anchor": "middle", "class": apagar(p.id).trim() });
      t.textContent = p.cliente.length > 16 ? p.cliente.slice(0, 15) + "…" : p.cliente;
    });
  }

  function mostrar(id) {
    Array.prototype.forEach.call(painel.children, function (c) { c.hidden = c.id !== id; });
    painel.scrollTop = 0;
    if (window.matchMedia("(max-width: 860px)").matches) painel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function selecionar(no) {
    sel = sel === no ? null : no;
    mostrar(sel ? "det-" + sel.id : "det-inicio");
    desenhar();
  }

  painel.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-abrir]");
    if (!b) return;
    var p = projetos.filter(function (x) { return x.id === b.getAttribute("data-abrir"); })[0];
    if (p) { sel = null; selecionar(p); }
  });

  desenhar();
  var scroll = svg.parentNode, central = dados.areas.filter(function (a) { return a.central; })[0];
  if (central && scroll.scrollWidth > scroll.clientWidth) {
    scroll.scrollLeft = (central.x / LARG) * scroll.scrollWidth - scroll.clientWidth / 2;
  }
})();
