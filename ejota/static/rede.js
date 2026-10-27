// Desenha as linhas entre cada bolha de projeto e as áreas, e centraliza Marketing.
(function () {
  "use strict";
  var ligacoes = JSON.parse(document.getElementById("dados-rede").textContent);
  var mapa = document.getElementById("mapa");
  var svg = document.getElementById("mapa-linhas");
  var scroll = document.getElementById("mapa-scroll");
  var NS = "http://www.w3.org/2000/svg";

  function centro(el, base) {
    var r = el.getBoundingClientRect();
    return { x: r.left - base.left + r.width / 2, y: r.top - base.top + r.height / 2, top: r.top - base.top, bottom: r.bottom - base.top };
  }

  function desenhar() {
    var base = mapa.getBoundingClientRect();
    svg.setAttribute("width", mapa.scrollWidth);
    svg.setAttribute("height", mapa.scrollHeight);
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var hubs = Array.prototype.slice.call(mapa.querySelectorAll(".hub"));
    for (var i = 1; i < hubs.length; i++) {
      var a = centro(hubs[i - 1], base), b = centro(hubs[i], base);
      linha(a.x, a.y, b.x, b.y, "espinha");
    }
    ligacoes.forEach(function (l) {
      var bolha = document.getElementById(l[0]), hub = document.getElementById(l[1]);
      if (!bolha || !hub) return;
      var b = centro(bolha, base), h = centro(hub, base);
      var acima = b.y < h.y;
      var y1 = acima ? b.bottom : b.top, y2 = acima ? h.top : h.bottom;
      var x1 = b.x, x2 = h.x, meio = (y1 + y2) / 2;
      var p = document.createElementNS(NS, "path");
      p.setAttribute("d", "M" + x1 + "," + y1 + " C" + x1 + "," + meio + " " + x2 + "," + meio + " " + x2 + "," + y2);
      p.setAttribute("class", l[2] ? "lig principal" : "lig");
      svg.appendChild(p);
    });
  }

  function linha(x1, y1, x2, y2, cls) {
    var l = document.createElementNS(NS, "line");
    l.setAttribute("x1", x1); l.setAttribute("y1", y1); l.setAttribute("x2", x2); l.setAttribute("y2", y2);
    l.setAttribute("class", cls);
    svg.appendChild(l);
  }

  function centralizar() {
    var central = mapa.querySelector(".hub.central");
    if (!central) return;
    scroll.scrollLeft = central.offsetLeft + central.offsetWidth / 2 - scroll.clientWidth / 2;
  }

  desenhar();
  centralizar();
  window.addEventListener("resize", desenhar);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(desenhar);
})();
