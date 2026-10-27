// Grafo da rede da Ejota: layout de forças simples, sem bibliotecas externas.
(function () {
  "use strict";
  var dados = JSON.parse(document.getElementById("dados-rede").textContent);
  var svg = document.getElementById("rede");
  var painel = document.getElementById("painel");
  var NS = "http://www.w3.org/2000/svg";
  var ativos = { projeto: true, area: true, causa: true, perfil: true, lacuna: true };
  var nos = dados.nos.map(function (n, i) {
    var ang = (2 * Math.PI * i) / dados.nos.length;
    var raio = n.tipo === "projeto" ? 140 : 260;
    return Object.assign({}, n, { x: Math.cos(ang) * raio, y: Math.sin(ang) * raio, vx: 0, vy: 0 });
  });
  var porId = {};
  nos.forEach(function (n) { porId[n.id] = n; });
  var arestas = dados.arestas.filter(function (a) { return porId[a.origem] && porId[a.destino]; });
  var selecionado = null, arrastando = null, energia = 1;

  function raio(n) { return n.tipo === "projeto" ? 6 + 5 * Math.sqrt(n.peso) : 5 + 3 * Math.sqrt(n.peso); }
  function visivel(n) { return ativos[n.tipo]; }

  function passo() {
    var vis = nos.filter(visivel), i, j;
    for (i = 0; i < vis.length; i++) {
      for (j = i + 1; j < vis.length; j++) {
        var a = vis[i], b = vis[j], dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy + 0.01;
        var f = 2600 / d2, d = Math.sqrt(d2);
        a.vx -= f * dx / d; a.vy -= f * dy / d; b.vx += f * dx / d; b.vy += f * dy / d;
      }
    }
    arestas.forEach(function (e) {
      var a = porId[e.origem], b = porId[e.destino];
      if (!visivel(a) || !visivel(b)) return;
      var dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1, f = (d - 90) * 0.02;
      a.vx += f * dx / d; a.vy += f * dy / d; b.vx -= f * dx / d; b.vy -= f * dy / d;
    });
    vis.forEach(function (n) {
      n.vx -= n.x * 0.01; n.vy -= n.y * 0.01;
      if (n === arrastando) { n.vx = n.vy = 0; return; }
      n.x += Math.max(-12, Math.min(12, n.vx * energia)); n.y += Math.max(-12, Math.min(12, n.vy * energia));
      n.vx *= 0.5; n.vy *= 0.5;
    });
    energia = Math.max(0.02, energia * 0.985);
  }

  function enquadrar() {
    var vis = nos.filter(visivel);
    if (!vis.length) return;
    var xs = vis.map(function (n) { return n.x; }), ys = vis.map(function (n) { return n.y; });
    var m = 40, x0 = Math.min.apply(null, xs) - m, y0 = Math.min.apply(null, ys) - m;
    var w = Math.max.apply(null, xs) + m - x0, h = Math.max.apply(null, ys) + m - y0;
    svg.setAttribute("viewBox", [x0, y0, w, h].join(" "));
  }

  function desenhar() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var vizinhos = {};
    if (selecionado) arestas.forEach(function (e) {
      if (e.origem === selecionado.id) vizinhos[e.destino] = 1;
      if (e.destino === selecionado.id) vizinhos[e.origem] = 1;
    });
    arestas.forEach(function (e) {
      var a = porId[e.origem], b = porId[e.destino];
      if (!visivel(a) || !visivel(b)) return;
      var l = document.createElementNS(NS, "line");
      l.setAttribute("x1", a.x); l.setAttribute("y1", a.y); l.setAttribute("x2", b.x); l.setAttribute("y2", b.y);
      l.setAttribute("stroke-width", Math.min(4, e.peso));
      var ligada = selecionado && (e.origem === selecionado.id || e.destino === selecionado.id);
      if (selecionado) l.setAttribute("opacity", ligada ? 1 : 0.15);
      if (ligada) l.style.stroke = "var(--accent)";
      svg.appendChild(l);
    });
    nos.filter(visivel).forEach(function (n) {
      var c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", n.x); c.setAttribute("cy", n.y); c.setAttribute("r", raio(n));
      c.setAttribute("class", "n-" + n.tipo + (n.tipo === "projeto" ? "-" + n.grupo : "") + (n === selecionado ? " sel" : ""));
      if (selecionado && n !== selecionado && !vizinhos[n.id]) c.setAttribute("opacity", 0.25);
      c.addEventListener("pointerdown", function (ev) { arrastando = n; selecionar(n); svg.setPointerCapture(ev.pointerId); ev.preventDefault(); });
      var t = document.createElementNS(NS, "title"); t.textContent = n.rotulo; c.appendChild(t);
      svg.appendChild(c);
      var tx = document.createElementNS(NS, "text");
      tx.setAttribute("x", n.x + raio(n) + 3); tx.setAttribute("y", n.y + 4);
      tx.textContent = n.rotulo;
      if (selecionado && n !== selecionado && !vizinhos[n.id]) tx.setAttribute("opacity", 0.25);
      svg.appendChild(tx);
    });
  }

  function texto(tag, conteudo) { var el = document.createElement(tag); el.textContent = conteudo; return el; }

  function selecionar(n) {
    selecionado = n;
    painel.replaceChildren();
    painel.appendChild(texto("h3", n.rotulo));
    var tipos = { projeto: "Projeto", area: "Área", causa: "Causa de atraso", perfil: "Porte do cliente", lacuna: "Lacuna de dados" };
    var sub = texto("p", tipos[n.tipo] || n.tipo); sub.className = "small muted"; sub.style.margin = "0 0 8px";
    painel.appendChild(sub);
    var dl = document.createElement("dl");
    n.metricas.forEach(function (par) { dl.appendChild(texto("dt", par[0])); dl.appendChild(texto("dd", par[1])); });
    painel.appendChild(dl);
    if (n.link && !document.getElementById("dados-rede").dataset.exportado) {
      var p = document.createElement("p"); p.className = "small"; p.style.margin = "10px 0 0";
      var a = texto("a", "Abrir projeto →"); a.href = n.link; p.appendChild(a); painel.appendChild(p);
    }
    desenhar();
  }

  function ponto(ev) {
    var pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }
  svg.addEventListener("pointermove", function (ev) {
    if (!arrastando) return;
    var p = ponto(ev); arrastando.x = p.x; arrastando.y = p.y; energia = Math.max(energia, 0.3); desenhar();
  });
  svg.addEventListener("pointerup", function () { arrastando = null; });
  document.getElementById("filtros").addEventListener("change", function (ev) {
    if (!ev.target.value) return;
    ativos[ev.target.value] = ev.target.checked;
    if (selecionado && !visivel(selecionado)) selecionado = null;
    energia = 1; animar(240);
  });

  function animar(passos) {
    var i = 0;
    (function quadro() {
      for (var k = 0; k < 3; k++) passo();
      if (!arrastando) enquadrar();
      desenhar();
      if (++i < passos) requestAnimationFrame(quadro);
    })();
  }
  for (var k = 0; k < 200; k++) passo();
  animar(120);
})();
