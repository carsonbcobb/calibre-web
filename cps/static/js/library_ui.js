(function () {
  function scrollRow(button) {
    var wrap = button.closest(".library-row-wrap");
    if (!wrap) {
      return;
    }
    var scroller = wrap.querySelector(".library-row-scroller");
    if (!scroller) {
      return;
    }
    var direction = parseInt(button.getAttribute("data-dir") || "1", 10);
    var distance = Math.max(scroller.clientWidth * 0.8, 220);
    scroller.scrollBy({ left: direction * distance, behavior: "smooth" });
  }

  document.addEventListener("click", function (event) {
    var send = event.target.closest(".library-send-kindle");
    if (send) {
      event.preventDefault();
      event.stopPropagation();
      var tokenInput = document.querySelector("input[name='csrf_token']");
      var body = "csrf_token=" + encodeURIComponent(tokenInput ? tokenInput.value : "");
      send.disabled = true;
      fetch(send.getAttribute("data-href"), {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "Accept": "application/json"
        },
        body: body,
        credentials: "same-origin"
      }).then(function (response) {
        return response.json();
      }).then(function (data) {
        var items = Array.isArray(data) ? data : [data];
        var text = items.map(function (item) { return item.message || ""; }).filter(Boolean).join(" ");
        send.textContent = text || "Sent";
      }).catch(function () {
        send.textContent = "Could not send this book.";
      });
      return;
    }
    var button = event.target.closest(".library-scroll");
    if (!button) {
      return;
    }
    event.preventDefault();
    scrollRow(button);
  });

  document.querySelectorAll(".library-hero").forEach(function (hero) {
    var slides = hero.querySelectorAll(".library-hero-slide");
    var dots = hero.querySelectorAll(".library-hero-dot");
    if (slides.length < 2) {
      return;
    }
    var index = 0;
    var timer = null;
    function show(next) {
      index = (next + slides.length) % slides.length;
      Array.prototype.forEach.call(slides, function (slide, i) {
        slide.classList.toggle("is-active", i === index);
      });
      Array.prototype.forEach.call(dots, function (dot, i) {
        dot.classList.toggle("is-active", i === index);
      });
    }
    function start() {
      timer = setInterval(function () { show(index + 1); }, 8000);
    }
    Array.prototype.forEach.call(dots, function (dot) {
      dot.addEventListener("click", function () {
        show(parseInt(dot.getAttribute("data-hero") || "0", 10));
      });
    });
    hero.addEventListener("mouseenter", function () {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    });
    hero.addEventListener("mouseleave", start);
    start();
  });

  var shuffle = document.getElementById("library-shuffle");
  if (shuffle) {
    shuffle.addEventListener("click", function (event) {
      event.preventDefault();
      var href = shuffle.getAttribute("href") || "/";
      var join = href.indexOf("?") === -1 ? "?" : "&";
      window.location = href + join + "shuffle=" + Date.now();
    });
  }

  var search = document.getElementById("query");
  var box = document.getElementById("library-suggest");
  if (search && box) {
    var pending = null;
    var matches = [];
    var active = -1;

    function closeSuggest() {
      box.hidden = true;
      box.innerHTML = "";
      matches = [];
      active = -1;
    }

    function markActive() {
      Array.prototype.forEach.call(box.querySelectorAll(".library-suggest-item"), function (link, index) {
        link.classList.toggle("is-active", index === active);
      });
    }

    function showMatches(rows) {
      box.innerHTML = "";
      matches = rows || [];
      active = -1;
      if (!matches.length) {
        closeSuggest();
        return;
      }
      matches.forEach(function (row) {
        var link = document.createElement("a");
        link.className = "library-suggest-item";
        link.href = row.url;
        var title = document.createElement("span");
        title.className = "library-suggest-title";
        title.textContent = row.title || "";
        var author = document.createElement("span");
        author.className = "library-suggest-author";
        author.textContent = row.author || "";
        link.appendChild(title);
        link.appendChild(author);
        box.appendChild(link);
      });
      box.hidden = false;
    }

    search.addEventListener("input", function () {
      var value = search.value.trim();
      if (pending) {
        clearTimeout(pending);
      }
      if (value.length < 2) {
        closeSuggest();
        return;
      }
      pending = setTimeout(function () {
        var endpoint = search.getAttribute("data-suggest") || "/library/suggest";
        var join = endpoint.indexOf("?") === -1 ? "?" : "&";
        fetch(endpoint + join + "q=" + encodeURIComponent(value), {
          credentials: "same-origin",
          headers: { "Accept": "application/json" }
        }).then(function (response) {
          return response.json();
        }).then(showMatches).catch(closeSuggest);
      }, 180);
    });

    search.addEventListener("keydown", function (event) {
      if (box.hidden || !matches.length) {
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        active = Math.min(matches.length - 1, active + 1);
        markActive();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        active = Math.max(0, active - 1);
        markActive();
      } else if (event.key === "Escape") {
        closeSuggest();
      } else if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        window.location = matches[active].url;
      }
    });

    document.addEventListener("click", function (event) {
      if (!box.hidden && !search.contains(event.target) && !box.contains(event.target)) {
        closeSuggest();
      }
    });
  }
})();
