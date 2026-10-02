(function () {
  function scrollRow(button) {
    var wrap = button.closest(".library-row-wrap") || button.closest(".cw-row-stage");
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

  function updateRowArrows(stage) {
    var scroller = stage.querySelector(".library-row-scroller");
    var prev = stage.querySelector(".cw-arrow-prev");
    var next = stage.querySelector(".cw-arrow-next");
    if (!scroller || !prev || !next) {
      return;
    }
    var max = scroller.scrollWidth - scroller.clientWidth;
    var canScroll = max > 8;
    prev.hidden = !canScroll || scroller.scrollLeft <= 8;
    next.hidden = !canScroll || scroller.scrollLeft >= max - 8;
  }

  function measureRows() {
    document.querySelectorAll(".cw-row-stage").forEach(updateRowArrows);
  }

  function bindScroller(scroller) {
    if (scroller.dataset.bound === "1") {
      return;
    }
    scroller.dataset.bound = "1";
    scroller.addEventListener("scroll", function () {
      var stage = scroller.closest(".cw-row-stage");
      if (stage) {
        updateRowArrows(stage);
      }
    }, { passive: true });
  }

  function bindRows() {
    document.querySelectorAll(".library-row-scroller").forEach(bindScroller);
    measureRows();
  }

  bindRows();
  window.addEventListener("resize", measureRows);
  window.addEventListener("load", measureRows);
  document.addEventListener("cw-rows-added", bindRows);

  function toast(message, isError) {
    var node = document.getElementById("cw-toast");
    if (!node) {
      node = document.createElement("div");
      node.id = "cw-toast";
      node.className = "cw-toast";
      node.setAttribute("role", "status");
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.classList.toggle("is-error", !!isError);
    node.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () {
      node.hidden = true;
    }, 2200);
  }

  function applyFlag(button, on) {
    button.classList.toggle("is-on", on);
    button.setAttribute("data-on", on ? "1" : "0");
    button.setAttribute("aria-pressed", on ? "true" : "false");
  }

  function applyFlagState(row, data) {
    ["want", "finished", "favorite"].forEach(function (kind) {
      var button = row.querySelector('.cw-flag[data-kind="' + kind + '"]');
      if (button && Object.prototype.hasOwnProperty.call(data, kind)) {
        applyFlag(button, !!data[kind]);
      }
    });
  }

  document.addEventListener("click", function (event) {
    var flag = event.target.closest(".cw-flag");
    if (!flag) {
      return;
    }
    event.preventDefault();
    var row = flag.closest(".cw-book-actions");
    if (!row || flag.dataset.busy === "1") {
      return;
    }
    var snapshot = {};
    row.querySelectorAll(".cw-flag").forEach(function (button) {
      snapshot[button.getAttribute("data-kind")] = button.getAttribute("data-on") === "1";
    });
    var kind = flag.getAttribute("data-kind");
    var next = snapshot[kind] !== true;
    applyFlag(flag, next);
    if (kind === "finished" && next) {
      var want = row.querySelector('.cw-flag[data-kind="want"]');
      if (want) {
        applyFlag(want, false);
      }
    }
    var tokenInput = row.querySelector("input[name='csrf_token']") || document.querySelector("input[name='csrf_token']");
    var body = "csrf_token=" + encodeURIComponent(tokenInput ? tokenInput.value : "")
      + "&kind=" + encodeURIComponent(kind)
      + "&on=" + (next ? "1" : "0");
    flag.dataset.busy = "1";
    fetch(row.getAttribute("data-flag-url"), {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
      },
      body: body,
      credentials: "same-origin"
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("flag");
      }
      return response.json();
    }).then(function (data) {
      applyFlagState(row, data);
      toast(next ? flag.getAttribute("data-on-toast") : flag.getAttribute("data-off-toast"));
    }).catch(function () {
      applyFlagState(row, snapshot);
      toast("Could not save that change", true);
    }).then(function () {
      flag.dataset.busy = "0";
    });
  });

  document.addEventListener("click", function (event) {
    var send = event.target.closest(".library-send-kindle");
    if (!send || send.tagName === "A") {
      return;
    }
    var href = send.getAttribute("data-href");
    if (!href) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    if (send.disabled || send.getAttribute("aria-busy") === "true") {
      return;
    }
    var tokenInput = document.querySelector("input[name='csrf_token']");
    var body = "csrf_token=" + encodeURIComponent(tokenInput ? tokenInput.value : "");
    send.disabled = true;
    send.setAttribute("aria-busy", "true");
    fetch(href, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
      },
      body: body,
      credentials: "same-origin"
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("send");
      }
      return response.json();
    }).then(function (data) {
      var items = Array.isArray(data) ? data : [data];
      var failed = items.some(function (item) {
        return item && item.type && item.type !== "success";
      });
      if (failed) {
        throw new Error("send");
      }
      toast(send.getAttribute("data-toast") || "Sent to Kindle");
    }).catch(function () {
      toast("Could not send this book.", true);
    }).then(function () {
      send.disabled = false;
      send.removeAttribute("aria-busy");
    });
  }, true);

  function keepInView(el) {
    if (!el) {
      return;
    }
    var limit = document.documentElement.clientWidth;
    el.style.left = "";
    el.style.right = "";
    var rect = el.getBoundingClientRect();
    if (rect.right > limit - 12) {
      el.style.left = "auto";
      el.style.right = "0";
    }
    rect = el.getBoundingClientRect();
    if (rect.left < 12) {
      el.style.left = "0";
      el.style.right = "auto";
    }
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest(".library-scroll");
    if (!button) {
      return;
    }
    event.preventDefault();
    scrollRow(button);
  });

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest(".dropdown-toggle, [data-toggle='dropdown']");
    if (!toggle) {
      return;
    }
    window.setTimeout(function () {
      var menu = toggle.parentElement && toggle.parentElement.querySelector(".dropdown-menu");
      keepInView(menu);
    }, 0);
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

  var discover = document.getElementById("cw-discover");
  if (discover) {
    var dataNode = document.getElementById("cw-discover-data");
    var books = [];
    try {
      books = JSON.parse(dataNode ? dataNode.textContent : "[]");
    } catch (error) {
      books = [];
    }
    var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var detail = discover.querySelector(".cw-discover-detail");
    var fan = discover.querySelector(".cw-discover-fan");
    var locked = false;

    function bookById(id) {
      var wanted = parseInt(id, 10);
      for (var index = 0; index < books.length; index += 1) {
        if (books[index].id === wanted) {
          return books[index];
        }
      }
      return null;
    }

    function text(field, value) {
      var node = discover.querySelector('[data-field="' + field + '"]');
      if (!node) {
        return;
      }
      node.textContent = value || "";
    }

    function showChip(name, value) {
      var chip = discover.querySelector('[data-chip="' + name + '"]');
      if (!chip) {
        return;
      }
      chip.hidden = !value;
      text(name, value || "");
    }

    function paintAccolades(tags) {
      var row = discover.querySelector('[data-field="accolades"]');
      if (!row) {
        return;
      }
      row.innerHTML = "";
      var list = Array.isArray(tags) ? tags.slice(0, 2) : [];
      row.hidden = !list.length;
      list.forEach(function (tag) {
        var chip = document.createElement("span");
        chip.className = "cw-accolade-tag is-" + (tag.tone || "note");
        chip.textContent = tag.label || "";
        row.appendChild(chip);
      });
    }

    function paintScore(book) {
      var chip = discover.querySelector('[data-chip="rating"]');
      if (!chip) {
        return;
      }
      var value = Number(book.rating);
      chip.innerHTML = "";
      if (!book.rating || !isFinite(value) || value <= 0) {
        chip.hidden = true;
        return;
      }
      chip.hidden = false;
      var number = value.toFixed(1);
      var count = book.rating_count ? String(book.rating_count) : "";
      var source = book.rating_source || "";
      var tip = count ? (source ? source + ", " + count + " ratings" : count + " ratings") : source;
      var wrap = document.createElement("span");
      wrap.className = "cw-score is-page";
      wrap.setAttribute("aria-label", number + " out of 5 stars");
      if (tip) {
        wrap.title = tip;
      }
      var num = document.createElement("span");
      num.className = "cw-score-num";
      num.textContent = number;
      wrap.appendChild(num);
      var row = document.createElement("span");
      row.className = "cw-score-row";
      row.setAttribute("aria-hidden", "true");
      var path = "M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z";
      for (var index = 0; index < 5; index += 1) {
        var raw = value - index;
        var pct = raw <= 0 ? 0 : (raw >= 1 ? 100 : Math.round(raw * 100));
        var star = document.createElement("span");
        star.className = "cw-star";
        star.innerHTML = '<svg viewBox="0 0 24 24" class="cw-star-empty"><path d="' + path + '"/></svg>'
          + '<svg viewBox="0 0 24 24" class="cw-star-fill" style="clip-path: inset(0 ' + (100 - pct) + '% 0 0)"><path d="' + path + '"/></svg>';
        row.appendChild(star);
      }
      wrap.appendChild(row);
      chip.appendChild(wrap);
    }

    function paint(book) {
      if (!book) {
        return;
      }
      var title = discover.querySelector('[data-field="title"]');
      if (title) {
        title.textContent = book.title || "";
        if (book.url) {
          title.setAttribute("href", book.url);
        }
      }
      text("author", book.author);
      var series = discover.querySelector('[data-field="series"]');
      if (series) {
        series.hidden = !book.series;
        series.textContent = book.series || "";
      }
      showChip("pages", book.pages);
      showChip("read_time", book.read_time);
      paintScore(book);
      var blurb = discover.querySelector('[data-field="blurb"]');
      if (blurb) {
        blurb.hidden = !book.blurb;
        blurb.textContent = book.blurb || "";
      }
      var source = discover.querySelector('[data-field="source"]');
      if (source) {
        source.hidden = !book.source_name;
        var sourceLink = source.querySelector("[data-field='source-link']");
        var sourceLabel = source.querySelector("[data-field='source-label']");
        var sourceText = book.source_name ? ("Source: " + book.source_name) : "";
        if (book.source_url) {
          if (!sourceLink) {
            source.textContent = "";
            sourceLink = document.createElement("a");
            sourceLink.setAttribute("data-field", "source-link");
            source.appendChild(sourceLink);
          }
          sourceLink.hidden = false;
          sourceLink.href = book.source_url;
          sourceLink.textContent = sourceText;
          if (sourceLabel) {
            sourceLabel.hidden = true;
          }
        } else if (sourceLabel) {
          sourceLabel.hidden = false;
          sourceLabel.textContent = sourceText;
          if (sourceLink) {
            sourceLink.hidden = true;
          }
        } else {
          source.textContent = sourceText;
        }
      }
      paintAccolades(book.accolades);
      var seriesCard = book.kind === "series";
      var view = discover.querySelector('[data-field="view"]');
      if (view) {
        view.hidden = !seriesCard;
        if (book.url) {
          view.setAttribute("href", book.url);
        }
      }
      var send = discover.querySelector('[data-field="send"]');
      if (send) {
        send.hidden = seriesCard || !book.send;
        if (book.send) {
          send.setAttribute("data-href", book.send);
        }
        if (book.send_toast) {
          send.setAttribute("data-toast", book.send_toast);
        } else {
          send.removeAttribute("data-toast");
        }
      }
      var note = discover.querySelector('[data-field="send_note"]');
      if (note) {
        note.hidden = true;
      }
      var more = discover.querySelector('[data-field="url"]');
      if (more) {
        more.setAttribute("href", book.url || "#");
      }
    }

    function preload(url) {
      return new Promise(function (resolve) {
        var settled = false;
        function finish() {
          if (settled) {
            return;
          }
          settled = true;
          resolve();
        }
        if (!url) {
          finish();
          return;
        }
        var image = new Image();
        image.onload = finish;
        image.onerror = finish;
        image.src = url;
        if (image.complete) {
          finish();
        }
        window.setTimeout(finish, 800);
      });
    }

    function crossfade(url) {
      if (!url) {
        return;
      }
      var layers = discover.querySelectorAll(".cw-discover-bg");
      if (!layers.length) {
        return;
      }
      var visible = discover.querySelector(".cw-discover-bg.is-visible") || layers[0];
      var next = layers[0] === visible ? layers[1] : layers[0];
      if (!next) {
        visible.style.backgroundImage = "url('" + url + "')";
        return;
      }
      if ((visible.style.backgroundImage || "").indexOf(url) !== -1 && visible.classList.contains("is-visible")) {
        return;
      }
      next.style.backgroundImage = "url('" + url + "')";
      next.classList.add("is-visible");
      visible.classList.remove("is-visible");
    }

    function reveal(book) {
      if (!detail) {
        paint(book);
        return;
      }
      detail.classList.remove("is-in");
      detail.classList.add("is-out");
      window.setTimeout(function () {
        paint(book);
        detail.classList.remove("is-out");
        detail.classList.add("is-in");
      }, reduceMotion ? 0 : 150);
    }

    function finish(delay) {
      window.setTimeout(function () {
        if (detail) {
          detail.classList.remove("is-in");
          detail.classList.remove("is-out");
        }
        if (fan) {
          fan.classList.remove("is-dim");
        }
        locked = false;
      }, delay);
    }

    function swap(clicked) {
      var from = clicked.getAttribute("data-slot") || "";
      if (locked || from === "1") {
        return;
      }
      var center = discover.querySelector('.cw-discover-cover[data-slot="1"]');
      var book = bookById(clicked.getAttribute("data-id"));
      if (!center || !book) {
        return;
      }
      locked = true;
      preload(book.cover).then(function () {
        if (reduceMotion && fan) {
          fan.classList.add("is-dim");
          window.setTimeout(function () {
            clicked.setAttribute("data-slot", "1");
            clicked.setAttribute("data-layer", "1");
            center.setAttribute("data-slot", from);
            center.setAttribute("data-layer", from);
            reveal(book);
            crossfade(book.cover);
            fan.classList.remove("is-dim");
            finish(220);
          }, 180);
          return;
        }
        clicked.setAttribute("data-slot", "1");
        center.setAttribute("data-slot", from);
        reveal(book);
        crossfade(book.cover);
        window.setTimeout(function () {
          clicked.setAttribute("data-layer", "1");
          center.setAttribute("data-layer", from);
        }, 275);
        finish(600);
      });
    }

    discover.addEventListener("click", function (event) {
      var cover = event.target.closest(".cw-discover-cover");
      if (cover) {
        swap(cover);
      }
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

  var sidebar = document.getElementById("cw-sidebar");
  var sidebarToggle = document.getElementById("cw-sidebar-toggle");
  var backdrop = document.getElementById("cw-backdrop");
  var railButton = document.getElementById("cw-side-rail");
  var filterInput = document.getElementById("cw-side-filter");
  var summaryUrl = sidebar ? sidebar.getAttribute("data-summary") : "";
  var userKey = sidebar ? (sidebar.getAttribute("data-user") || "0") : "0";
  var mobileQuery = window.matchMedia("(max-width: 800px)");

  function closeDrawer() {
    document.body.classList.remove("cw-sidebar-open");
    if (backdrop) {
      backdrop.hidden = true;
    }
  }

  function openDrawer() {
    document.body.classList.add("cw-sidebar-open");
    if (backdrop) {
      backdrop.hidden = false;
    }
  }

  function setRail(on) {
    document.body.classList.toggle("cw-sidebar-rail", on);
    try {
      localStorage.setItem("cw-side-rail:" + userKey, on ? "1" : "0");
    } catch (error) {
      return;
    }
    if (railButton) {
      railButton.title = on ? "Expand sidebar" : "Collapse sidebar";
    }
  }

  function savedGroups() {
    try {
      return JSON.parse(localStorage.getItem("cw-side-groups:" + userKey) || "{}");
    } catch (error) {
      return {};
    }
  }

  function rememberGroups() {
    if (!sidebar) {
      return;
    }
    var state = savedGroups();
    sidebar.querySelectorAll(".cw-group").forEach(function (group) {
      state[group.getAttribute("data-group")] = group.classList.contains("is-open");
      var toggle = group.querySelector(".cw-side-toggle");
      if (toggle) {
        toggle.setAttribute("aria-expanded", group.classList.contains("is-open") ? "true" : "false");
      }
    });
    try {
      localStorage.setItem("cw-side-groups:" + userKey, JSON.stringify(state));
    } catch (error) {
      return;
    }
  }

  function pageName() {
    return (document.body.className || "").split(/\s+/)[0] || "";
  }

  if (sidebar) {
    var stored = savedGroups();
    var currentPage = pageName();
    sidebar.querySelectorAll(".cw-group").forEach(function (group) {
      var pages = (group.getAttribute("data-pages") || "").split(",");
      var open = !!stored[group.getAttribute("data-group")];
      if (pages.indexOf(currentPage) !== -1) {
        open = true;
      }
      group.classList.toggle("is-open", open);
      var toggle = group.querySelector(".cw-side-toggle");
      if (toggle) {
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
      }
    });
    if (!mobileQuery.matches && localStorage.getItem("cw-side-rail:" + userKey) === "1") {
      document.body.classList.add("cw-sidebar-rail");
    }
    sidebar.addEventListener("click", function (event) {
      var toggle = event.target.closest(".cw-side-toggle");
      if (toggle) {
        var group = toggle.closest(".cw-group");
        if (document.body.classList.contains("cw-sidebar-rail") && !mobileQuery.matches) {
          setRail(false);
          group.classList.add("is-open");
          rememberGroups();
          return;
        }
        group.classList.toggle("is-open");
        rememberGroups();
        return;
      }
      if (mobileQuery.matches && event.target.closest("a")) {
        closeDrawer();
      }
    });
  }

  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", function () {
      if (mobileQuery.matches) {
        if (document.body.classList.contains("cw-sidebar-open")) {
          closeDrawer();
        } else {
          openDrawer();
        }
      } else {
        setRail(!document.body.classList.contains("cw-sidebar-rail"));
      }
    });
  }
  if (railButton) {
    railButton.addEventListener("click", function () {
      if (mobileQuery.matches) {
        closeDrawer();
        return;
      }
      setRail(!document.body.classList.contains("cw-sidebar-rail"));
    });
  }
  if (backdrop) {
    backdrop.addEventListener("click", closeDrawer);
  }

  var searchButton = document.getElementById("cw-side-search");
  function focusSearch() {
    var field = document.getElementById("query");
    if (!field) {
      return;
    }
    field.focus();
    if (typeof field.select === "function") {
      field.select();
    }
  }
  if (searchButton) {
    searchButton.addEventListener("click", focusSearch);
  }
  document.addEventListener("keydown", function (event) {
    if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) {
      return;
    }
    var target = event.target;
    var tag = target && target.tagName ? target.tagName.toLowerCase() : "";
    if (tag === "input" || tag === "textarea" || (target && target.isContentEditable)) {
      return;
    }
    event.preventDefault();
    focusSearch();
  });

  function applyFilter() {
    if (!sidebar || !filterInput) {
      return;
    }
    var query = filterInput.value.trim().toLowerCase();
    sidebar.querySelectorAll(".cw-side-link").forEach(function (link) {
      if (link.classList.contains("cw-side-toggle")) {
        return;
      }
      var name = (link.getAttribute("title") || link.textContent || "").toLowerCase();
      link.classList.toggle("is-hidden", !!query && name.indexOf(query) === -1);
    });
  }

  if (filterInput) {
    filterInput.addEventListener("input", applyFilter);
  }

  function fillCount(name, value) {
    if (!sidebar || value === null || value === undefined) {
      return;
    }
    sidebar.querySelectorAll('[data-count="' + name + '"] .cw-side-count').forEach(function (pill) {
      pill.textContent = String(value);
      pill.hidden = false;
    });
  }

  function fillList(kind, rows) {
    if (!sidebar) {
      return;
    }
    var list = sidebar.querySelector('.cw-sub-list[data-list="' + kind + '"]');
    if (!list) {
      return;
    }
    list.textContent = "";
    (rows || []).forEach(function (row) {
      var link = document.createElement("a");
      link.className = "cw-side-child";
      link.href = row.url;
      link.title = row.name;
      link.setAttribute("data-name", row.name);
      var label = document.createElement("span");
      label.className = "cw-side-text";
      label.textContent = row.name;
      var count = document.createElement("span");
      count.className = "cw-side-count";
      count.textContent = String(row.count);
      link.appendChild(label);
      link.appendChild(count);
      list.appendChild(link);
    });
    if (!rows || !rows.length) {
      var note = document.createElement("p");
      note.className = "cw-side-note";
      note.textContent = "Nothing here yet";
      list.appendChild(note);
    }
  }

  if (sidebar && summaryUrl) {
    fetch(summaryUrl, { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        ["books", "unread", "read", "favorites", "archived", "hot", "downloaded", "publishers", "languages", "ratings", "formats", "genre_count", "series_count"].forEach(function (name) {
          fillCount(name, data[name]);
        });
        applyFilter();
      })
      .catch(function () {
        sidebar.querySelectorAll(".cw-sub-list").forEach(function (list) {
          if (!list.children.length) {
            var note = document.createElement("p");
            note.className = "cw-side-note";
            note.textContent = "Could not load this list";
            list.appendChild(note);
          }
        });
      });
  }
})();

(function () {
  var genreBrowser = document.getElementById("cw-genre-browser");
  var genrePills = document.getElementById("cw-genre-pills");
  if (genreBrowser && genrePills) {
    genrePills.addEventListener("click", function (event) {
      var pill = event.target.closest(".cw-genre-chip");
      if (!pill || !genrePills.contains(pill)) {
        return;
      }
      var genreId = pill.getAttribute("data-genre");
      if (genreId === null) {
        return;
      }
      event.preventDefault();
      genrePills.querySelectorAll(".cw-genre-chip").forEach(function (item) {
        item.classList.toggle("is-on", item === pill);
      });
      genreBrowser.querySelectorAll(".library-row-wrap").forEach(function (row) {
        row.classList.toggle("is-hidden", !!genreId && row.id !== genreId);
      });
      if (genreId) {
        var target = document.getElementById(genreId);
        if (target) {
          target.scrollIntoView({ block: "nearest" });
        }
      }
    });
  }

  var seriesBrowser = document.getElementById("cw-series-browser");
  if (!seriesBrowser) {
    return;
  }
  var grid = document.getElementById("cw-series-grid");
  var search = document.getElementById("cw-series-search");
  var sort = document.getElementById("cw-series-sort");
  var progress = document.getElementById("cw-series-progress");
  var fresh = document.getElementById("cw-series-new");
  if (!grid) {
    return;
  }

  function applySeries() {
    var query = (search && search.value || "").trim().toLowerCase();
    var wantProgress = !!(progress && progress.checked);
    var wantFresh = !!(fresh && fresh.checked);
    var cards = Array.prototype.slice.call(grid.querySelectorAll(".cw-series-card"));
    var visible = 0;
    cards.forEach(function (card) {
      var name = (card.getAttribute("data-name") || "").toLowerCase();
      var state = card.getAttribute("data-state") || "";
      var nameOk = !query || name.indexOf(query) !== -1;
      var stateOk = true;
      if (wantProgress || wantFresh) {
        stateOk = (wantProgress && state === "progress") || (wantFresh && state === "new");
      }
      var show = nameOk && stateOk;
      card.classList.toggle("is-hidden", !show);
      if (show) {
        visible += 1;
      }
    });
    var mode = sort ? sort.value : "name";
    cards.sort(function (left, right) {
      if (mode === "count") {
        return Number(right.getAttribute("data-count") || 0) - Number(left.getAttribute("data-count") || 0);
      }
      if (mode === "updated") {
        return String(right.getAttribute("data-updated") || "").localeCompare(String(left.getAttribute("data-updated") || ""));
      }
      return String(left.getAttribute("data-name") || "").localeCompare(String(right.getAttribute("data-name") || ""));
    });
    cards.forEach(function (card) {
      grid.appendChild(card);
    });
    if (visible === 0) {
      cards.forEach(function (card) {
        card.classList.remove("is-hidden");
      });
    }
  }

  [search, sort, progress, fresh].forEach(function (control) {
    if (!control) {
      return;
    }
    control.addEventListener("input", applySeries);
    control.addEventListener("change", applySeries);
  });
})();

(function () {
  var page = document.getElementById("cw-discover-page");
  if (!page) {
    return;
  }
  var rowHost = document.getElementById("cw-discover-rows");
  var rows = [];
  var grid = document.getElementById("cw-discover-more");
  var keep = document.getElementById("cw-discover-keep");
  var sentinel = document.getElementById("cw-discover-sentinel");
  var countNode = document.getElementById("cw-discover-count");
  var endNode = document.getElementById("cw-discover-end");
  var roll = document.getElementById("cw-discover-roll");
  var debugNode = document.getElementById("cw-discover-debug");
  var reroll = document.getElementById("cw-discover-reroll");
  var moreButton = document.getElementById("cw-genre-more");
  var pop = document.getElementById("cw-genre-pop");
  var find = document.getElementById("cw-genre-find");
  var shown = new Set();
  var baseShown = parseInt(page.getAttribute("data-shown") || "0", 10) || 0;
  var genre = "";
  var busy = false;
  var moreDone = false;
  var gridOffset = 0;
  var gridCount = 0;
  var total = 0;
  var rowWatcher = null;
  var requestId = 0;

  function token() {
    var input = page.querySelector("input[name='csrf_token']");
    return input ? input.value : "";
  }

  function fetchShelf(kind, offset) {
    var body = "csrf_token=" + encodeURIComponent(token())
      + "&kind=" + encodeURIComponent(kind)
      + "&seed=" + encodeURIComponent(page.getAttribute("data-seed") || "")
      + "&genre=" + encodeURIComponent(genre)
      + "&panel=" + encodeURIComponent(page.getAttribute("data-exclude") || "")
      + "&offset=" + encodeURIComponent(offset || 0)
      + "&debug=" + encodeURIComponent(page.getAttribute("data-debug") || "");
    return fetch(page.getAttribute("data-url"), {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
      },
      body: body,
      credentials: "same-origin"
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("discover");
      }
      return response.json();
    });
  }

  function remember(ids) {
    (ids || []).forEach(function (id) {
      shown.add(String(id));
    });
    paintCount();
    maybeEnd();
  }

  function paintCount() {
    if (!countNode) {
      return;
    }
    var pattern = page.getAttribute("data-count") || "Showing {shown} of {total} books";
    countNode.textContent = pattern.replace("{shown}", String(baseShown + shown.size)).replace("{total}", String(total));
  }

  function maybeEnd() {
    if (!endNode) {
      return;
    }
    endNode.hidden = !(total > 0 && shown.size >= total && moreDone);
  }

  function rowsDone() {
    return rows.length === 0 || rows.every(function (row) {
      return row.getAttribute("data-state") === "done";
    });
  }

  function pump() {
    if (busy) {
      return;
    }
    var next = null;
    for (var i = 0; i < rows.length; i += 1) {
      var state = rows[i].getAttribute("data-state");
      if (state === "wait" || state === "queued") {
        next = rows[i];
        break;
      }
    }
    if (!next || next.getAttribute("data-state") !== "queued") {
      if (rowsDone()) {
        if (keep) {
          keep.hidden = gridCount === 0;
        }
        if (gridCount === 0) {
          moreDone = true;
          maybeEnd();
        } else if (sentinel && inView(sentinel)) {
          loadMore();
        }
      }
      return;
    }
    busy = true;
    next.setAttribute("data-state", "loading");
    var generation = requestId;
    fetchShelf(next.getAttribute("data-kind")).then(function (data) {
      if (generation !== requestId || !page.contains(next)) {
        return;
      }
      remember(data.ids);
      if (data.html) {
        next.innerHTML = data.html;
        next.hidden = false;
        next.style.minHeight = "";
        next.setAttribute("data-filled", "1");
        document.dispatchEvent(new CustomEvent("cw-rows-added"));
      } else {
        next.hidden = true;
      }
      next.setAttribute("data-state", "done");
    }).catch(function () {
      if (generation !== requestId || !page.contains(next)) {
        return;
      }
      next.setAttribute("data-state", "done");
    }).then(function () {
      if (generation !== requestId) {
        return;
      }
      busy = false;
      revealNext();
    });
  }

  function revealNext() {
    for (var i = 0; i < rows.length; i += 1) {
      var state = rows[i].getAttribute("data-state");
      if (state === "loading") {
        return;
      }
      if (state === "done") {
        continue;
      }
      rows[i].hidden = false;
      rows[i].style.minHeight = rows[i].getAttribute("data-filled") === "1" ? "" : "1px";
      if (state === "wait") {
        rows[i].setAttribute("data-state", "queued");
      }
      if (inView(rows[i])) {
        pump();
      }
      return;
    }
    pump();
  }

  function inView(node) {
    var box = node.getBoundingClientRect();
    return box.top < window.innerHeight + 240 && box.bottom > -240;
  }

  function loadMore() {
    if (busy || moreDone || !grid) {
      return;
    }
    if (!rowsDone()) {
      return;
    }
    busy = true;
    var generation = requestId;
    fetchShelf("more", gridOffset).then(function (data) {
      if (generation !== requestId) {
        return;
      }
      var ids = data.ids || [];
      remember(ids);
      gridOffset += ids.length;
      if (data.html) {
        grid.insertAdjacentHTML("beforeend", data.html);
        document.dispatchEvent(new CustomEvent("cw-rows-added"));
      }
      if (data.done || !ids.length) {
        moreDone = true;
        if (keep && grid && !grid.children.length) {
          keep.hidden = true;
        }
        maybeEnd();
      }
    }).catch(function () {
      if (generation !== requestId) {
        return;
      }
      moreDone = true;
      maybeEnd();
    }).then(function () {
      if (generation !== requestId) {
        return;
      }
      busy = false;
      if (!moreDone && sentinel && inView(sentinel)) {
        loadMore();
      }
    });
  }

  function bindRows() {
    if (rowWatcher) {
      rowWatcher.disconnect();
      rowWatcher = null;
    }
    if ("IntersectionObserver" in window) {
      rowWatcher = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting || entry.target.hidden) {
            return;
          }
          if (entry.target.getAttribute("data-state") === "wait") {
            entry.target.setAttribute("data-state", "queued");
          }
          pump();
        });
      }, { rootMargin: "240px" });
      rows.forEach(function (row) {
        rowWatcher.observe(row);
      });
      revealNext();
      return;
    }
    rows.forEach(function (row) {
      row.hidden = false;
      row.setAttribute("data-state", "queued");
    });
    pump();
  }

  function buildRows(list) {
    if (rowHost) {
      rowHost.innerHTML = "";
    }
    rows = (list || []).map(function (item) {
      var section = document.createElement("section");
      section.className = "cw-discover-slot";
      section.setAttribute("data-discover-row", "");
      section.setAttribute("data-kind", item.key);
      section.setAttribute("data-state", "wait");
      section.hidden = true;
      rowHost.appendChild(section);
      return section;
    });
    bindRows();
  }

  function reload() {
    requestId += 1;
    var generation = requestId;
    moreDone = false;
    busy = false;
    gridOffset = 0;
    gridCount = 0;
    shown = new Set();
    baseShown = 0;
    if (grid) {
      grid.innerHTML = "";
    }
    if (keep) {
      keep.hidden = true;
    }
    if (endNode) {
      endNode.hidden = true;
    }
    if (debugNode) {
      debugNode.innerHTML = "";
    }
    fetchShelf("plan").then(function (data) {
      if (generation !== requestId) {
        return;
      }
      total = data.total || 0;
      gridCount = data.grid_count || 0;
      remember(data.counted);
      if (debugNode && data.debug_html) {
        debugNode.innerHTML = data.debug_html;
      }
      buildRows(data.rows || []);
      if (!rows.length) {
        if (keep) {
          keep.hidden = gridCount === 0;
        }
        if (gridCount === 0) {
          moreDone = true;
          maybeEnd();
        } else if (sentinel && inView(sentinel)) {
          loadMore();
        }
      }
    }).catch(function (error) {
      if (generation !== requestId) {
        return;
      }
      if (window.console && console.error) {
        console.error(error);
      }
    });
  }

  page.querySelectorAll(".cw-genre-chip[data-genre]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      if (chip.id === "cw-genre-more") {
        return;
      }
      genre = chip.getAttribute("data-genre") || "";
      page.querySelectorAll(".cw-genre-chip").forEach(function (item) {
        item.classList.toggle("is-on", item === chip);
      });
      if (moreButton && chip.parentNode !== (pop && pop.querySelector(".cw-genre-pop-list"))) {
        moreButton.textContent = moreButton.getAttribute("data-label") || "More";
        moreButton.classList.remove("is-on");
      }
      if (pop && chip.closest(".cw-genre-pop")) {
        moreButton.textContent = chip.textContent;
        moreButton.classList.add("is-on");
        pop.hidden = true;
        moreButton.setAttribute("aria-expanded", "false");
      }
      reload();
    });
  });

  function keepInView(el) {
    var limit = document.documentElement.clientWidth;
    el.style.left = "";
    el.style.right = "";
    var rect = el.getBoundingClientRect();
    if (rect.right > limit - 12) {
      el.style.left = "auto";
      el.style.right = "0";
    }
  }

  if (moreButton && pop) {
    moreButton.addEventListener("click", function () {
      pop.hidden = !pop.hidden;
      moreButton.setAttribute("aria-expanded", pop.hidden ? "false" : "true");
      if (!pop.hidden) {
        keepInView(pop);
        if (find) {
          find.focus();
        }
      }
    });
    document.addEventListener("click", function (event) {
      if (pop.hidden) {
        return;
      }
      if (event.target.closest("#cw-genre-pop") || event.target.closest("#cw-genre-more")) {
        return;
      }
      pop.hidden = true;
      moreButton.setAttribute("aria-expanded", "false");
    });
  }

  if (find && pop) {
    find.addEventListener("input", function () {
      var query = find.value.trim().toLowerCase();
      pop.querySelectorAll(".cw-genre-chip").forEach(function (chip) {
        var name = chip.textContent.toLowerCase();
        chip.hidden = !!query && name.indexOf(query) === -1;
      });
    });
  }

  if (reroll) {
    reroll.addEventListener("click", function () {
      page.setAttribute("data-seed", String(Date.now()));
      reroll.classList.remove("is-spin");
      void reroll.offsetWidth;
      reroll.classList.add("is-spin");
      reload();
    });
    reroll.addEventListener("animationend", function () {
      reroll.classList.remove("is-spin");
    });
  }

  if (roll) {
    roll.addEventListener("click", function () {
      if (reroll) {
        reroll.click();
      }
    });
  }

  if (sentinel && "IntersectionObserver" in window) {
    var moreWatcher = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          loadMore();
        }
      });
    }, { rootMargin: "480px" });
    moreWatcher.observe(sentinel);
  }

  if (page.getAttribute("data-ready") === "1") {
    total = parseInt(page.getAttribute("data-total") || "0", 10) || 0;
    gridOffset = parseInt(page.getAttribute("data-grid-offset") || "0", 10) || 0;
    gridCount = parseInt(page.getAttribute("data-grid-count") || "0", 10) || 0;
    rows = rowHost ? Array.prototype.slice.call(rowHost.querySelectorAll("[data-discover-row]")) : [];
    if (gridCount > 0 && gridOffset >= gridCount) {
      moreDone = true;
      maybeEnd();
    }
    if (rows.length) {
      bindRows();
    } else if (!moreDone && sentinel && inView(sentinel)) {
      loadMore();
    }
  } else {
    reload();
  }
})();

(function () {
  var collage = document.getElementById("cw-login-collage");
  if (!collage) {
    return;
  }
  var narrow = window.matchMedia("(max-width: 720px)").matches;
  var coverW = narrow ? 110 : 148;
  var coverH = narrow ? 165 : 222;
  var gap = 14;
  var visible = Math.max(4, Math.ceil(window.innerWidth / (coverW + gap)));
  var perRow = visible * 2;
  var rows = Math.max(5, Math.ceil((window.innerHeight * 1.35) / (coverH + gap)));
  while (rows * perRow * 2 > 300 && perRow > visible) {
    perRow -= 1;
  }
  while (rows * perRow * 2 > 300 && rows > 5) {
    rows -= 1;
  }

  function shuffle(list) {
    var copy = list.slice();
    for (var index = copy.length - 1; index > 0; index -= 1) {
      var swap = Math.floor(Math.random() * (index + 1));
      var hold = copy[index];
      copy[index] = copy[swap];
      copy[swap] = hold;
    }
    return copy;
  }

  function preferFresh(books) {
    var seen = {};
    try {
      JSON.parse(localStorage.getItem("cw-login-seen") || "[]").forEach(function (id) {
        seen[id] = true;
      });
    } catch (error) {
      seen = {};
    }
    var mixed = shuffle(books);
    if (books.length <= rows * perRow) {
      return mixed;
    }
    var fresh = [];
    var again = [];
    mixed.forEach(function (book) {
      (seen[book.id] ? again : fresh).push(book);
    });
    return fresh.concat(again);
  }

  function genreOrder(books) {
    var groups = {};
    var keys = [];
    books.forEach(function (book) {
      var key = book.genre || "other";
      if (!groups[key]) {
        groups[key] = [];
        keys.push(key);
      }
      groups[key].push(book);
    });
    keys = shuffle(keys);
    var ordered = [];
    var guard = 0;
    while (ordered.length < books.length && guard < books.length * 3) {
      keys.forEach(function (key) {
        var bucket = groups[key];
        if (bucket && bucket.length) {
          ordered.push(bucket.shift());
        }
      });
      guard += 1;
    }
    return ordered;
  }

  function tooClose(row, book, distance) {
    var start = Math.max(0, row.length - distance);
    var index;
    for (index = start; index < row.length; index += 1) {
      if (row[index].id === book.id) {
        return true;
      }
    }
    for (index = 0; index < row.length && index < distance; index += 1) {
      if ((perRow - row.length) + index <= distance && row[index].id === book.id) {
        return true;
      }
    }
    return false;
  }

  function countAuthor(row, author) {
    if (!author) {
      return 0;
    }
    var count = 0;
    row.forEach(function (book) {
      if (book.author === author) {
        count += 1;
      }
    });
    return count;
  }

  function hasSeries(row, series) {
    if (!series) {
      return false;
    }
    return row.some(function (book) {
      return book.series === series;
    });
  }

  function canPlace(built, rowIndex, book, seriesScreen, rules) {
    var row = built[rowIndex];
    var above = built[rowIndex - 1];
    if (rules.unique && rules.used[book.id]) {
      return false;
    }
    if (above && above[row.length] && above[row.length].id === book.id) {
      return false;
    }
    if (tooClose(row, book, rules.distance)) {
      return false;
    }
    if (rules.series && book.series && (hasSeries(row, book.series) || (seriesScreen[book.series] || 0) >= 2)) {
      return false;
    }
    if (rules.author && countAuthor(row, book.author) >= 2) {
      return false;
    }
    if (rules.genre && row.length && book.genre && row[row.length - 1].genre === book.genre) {
      return false;
    }
    return true;
  }

  function place(built, rowIndex, book, seriesScreen, used) {
    built[rowIndex].push(book);
    used[book.id] = true;
    if (book.series) {
      seriesScreen[book.series] = (seriesScreen[book.series] || 0) + 1;
    }
  }

  function build(books) {
    var ordered = genreOrder(preferFresh(books));
    var built = [];
    var used = {};
    var seriesScreen = {};
    var rowIndex;
    for (rowIndex = 0; rowIndex < rows; rowIndex += 1) {
      built.push([]);
    }
    var passes = [
      { unique: true, distance: Math.max(6, visible), series: true, author: true, genre: true },
      { unique: true, distance: 6, series: true, author: true, genre: false },
      { unique: false, distance: Math.max(6, visible), series: true, author: true, genre: true },
      { unique: false, distance: 6, series: true, author: true, genre: false },
      { unique: false, distance: 6, series: true, author: false, genre: false },
      { unique: false, distance: 1, series: false, author: false, genre: false }
    ];
    passes.forEach(function (rules) {
      rules.used = used;
      for (rowIndex = 0; rowIndex < rows; rowIndex += 1) {
        if (built[rowIndex].length >= perRow || !ordered.length) {
          continue;
        }
        var offset = (rowIndex * 5 + 1) % ordered.length;
        var turned = ordered.slice(offset).concat(ordered.slice(0, offset));
        if (rowIndex % 2) {
          turned.reverse();
        }
        var guard = 0;
        var index = 0;
        while (built[rowIndex].length < perRow && guard < turned.length * 2) {
          var book = turned[index % turned.length];
          index += 1;
          guard += 1;
          if (canPlace(built, rowIndex, book, seriesScreen, rules)) {
            place(built, rowIndex, book, seriesScreen, used);
          }
        }
      }
    });
    return built;
  }

  var showed = false;
  function show() {
    if (showed) {
      return;
    }
    showed = true;
    collage.classList.add("is-ready");
  }

  function render(built) {
    var shown = {};
    collage.textContent = "";
    built.forEach(function (row, rowIndex) {
      if (!row.length) {
        return;
      }
      var line = document.createElement("div");
      line.className = "library-login-row";
      var track = document.createElement("div");
      track.className = "library-login-row-track";
      var duration = 60 + ((rowIndex * 47) % 61);
      var delay = Math.round(duration * ((rowIndex * 0.37) % 1));
      track.style.animationDuration = duration + "s";
      track.style.animationDelay = "-" + delay + "s";
      var copy;
      for (copy = 0; copy < 2; copy += 1) {
        var set = document.createElement("div");
        set.className = "library-login-row-set";
        row.forEach(function (book) {
          shown[book.id] = true;
          var image = document.createElement("img");
          image.src = book.url;
          image.alt = "";
          image.width = coverW;
          image.height = coverH;
          image.loading = "lazy";
          image.decoding = "async";
          image.addEventListener("load", show);
          image.addEventListener("error", function () {
            image.remove();
          });
          set.appendChild(image);
        });
        track.appendChild(set);
      }
      line.appendChild(track);
      collage.appendChild(line);
    });
    try {
      localStorage.setItem("cw-login-seen", JSON.stringify(Object.keys(shown).map(Number)));
    } catch (error) {
      return;
    }
  }

  if (document.hidden) {
    collage.classList.add("is-paused");
  }
  document.addEventListener("visibilitychange", function () {
    collage.classList.toggle("is-paused", document.hidden);
  });

  fetch(collage.getAttribute("data-url"), {
    credentials: "same-origin",
    headers: { "Accept": "application/json" }
  }).then(function (response) {
    return response.json();
  }).then(function (books) {
    if (!Array.isArray(books) || !books.length) {
      return;
    }
    render(build(books));
    window.setTimeout(show, 1200);
  }).catch(function () {
    return null;
  });
})();

(function () {
  function toast(message, isError) {
    var node = document.getElementById("cw-toast");
    if (!node) {
      node = document.createElement("div");
      node.id = "cw-toast";
      node.className = "cw-toast";
      node.setAttribute("role", "status");
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.classList.toggle("is-error", !!isError);
    node.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () {
      node.hidden = true;
    }, 2400);
  }

  function csrf() {
    var input = document.querySelector("input[name='csrf_token']");
    return input ? input.value : "";
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
      },
      body: body,
      credentials: "same-origin"
    }).then(function (response) {
      return response.json().then(function (data) {
        data = data || {};
        data._ok = response.ok;
        return data;
      });
    });
  }

  var modal = document.getElementById("cw-friend-modal");
  var form = document.getElementById("cw-friend-form");
  if (modal && form) {
    var title = document.getElementById("cw-friend-modal-title");
    var error = form.querySelector(".cw-friend-error");

    function openForm(friend) {
      form.elements.id.value = friend ? friend.id : "";
      form.elements.name.value = friend ? friend.name : "";
      form.elements.kindle_email.value = friend ? friend.email : "";
      title.textContent = friend ? "Edit friend" : "Add friend";
      error.hidden = true;
      modal.hidden = false;
      form.elements.name.focus();
    }

    function closeForm() {
      modal.hidden = true;
    }

    document.querySelectorAll("#cw-add-friend, [data-add]").forEach(function (button) {
      button.addEventListener("click", function () {
        openForm(null);
      });
    });
    document.querySelectorAll("[data-edit]").forEach(function (button) {
      button.addEventListener("click", function () {
        var card = button.closest(".cw-friend-card");
        openForm({
          id: card.getAttribute("data-id"),
          name: card.getAttribute("data-name"),
          email: card.getAttribute("data-email")
        });
      });
    });
    document.querySelectorAll("[data-delete]").forEach(function (button) {
      button.addEventListener("click", function () {
        var card = button.closest(".cw-friend-card");
        var name = card.getAttribute("data-name") || "this friend";
        if (!window.confirm("Remove " + name + "?")) {
          return;
        }
        var body = "csrf_token=" + encodeURIComponent(csrf());
        post("/friends/" + card.getAttribute("data-id") + "/delete", body).then(function () {
          window.location.reload();
        }).catch(function () {
          toast("Could not remove that friend.", true);
        });
      });
    });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var body = "csrf_token=" + encodeURIComponent(csrf())
        + "&id=" + encodeURIComponent(form.elements.id.value)
        + "&name=" + encodeURIComponent(form.elements.name.value)
        + "&kindle_email=" + encodeURIComponent(form.elements.kindle_email.value);
      post("/friends/save", body).then(function (data) {
        if (!data._ok) {
          error.textContent = data.message || "Could not save that friend.";
          error.hidden = false;
          return;
        }
        window.location.reload();
      }).catch(function () {
        error.textContent = "Could not save that friend.";
        error.hidden = false;
      });
    });
    modal.addEventListener("click", function (event) {
      if (event.target === modal || event.target.closest("[data-close='form']")) {
        closeForm();
      }
    });
  }

  var opener = document.getElementById("cw-send-friend");
  var picker = document.getElementById("cw-friend-picker");
  if (!opener || !picker) {
    return;
  }
  var list = picker.querySelector(".cw-friend-picker-list");
  var search = picker.querySelector(".cw-friend-search");
  var empty = picker.querySelector(".cw-friend-none");
  var sendButton = document.getElementById("cw-friend-send");
  var friends = [];
  var sendLabel = "Send";

  function selectedIds() {
    return Array.prototype.map.call(list.querySelectorAll("input:checked"), function (input) {
      return input.value;
    });
  }

  function updateSend() {
    var count = selectedIds().length;
    if (count === 0) {
      sendButton.textContent = sendLabel;
      sendButton.disabled = true;
      return;
    }
    sendButton.disabled = false;
    sendButton.textContent = count === 1 ? "Send to 1 friend" : "Send to " + count + " friends";
  }

  function render(filter) {
    var query = (filter || "").trim().toLowerCase();
    list.textContent = "";
    var shown = 0;
    friends.forEach(function (friend) {
      var haystack = (friend.name + " " + friend.email).toLowerCase();
      if (query && haystack.indexOf(query) === -1) {
        return;
      }
      shown += 1;
      var row = document.createElement("label");
      row.className = "cw-friend-choice";
      var box = document.createElement("input");
      box.type = "checkbox";
      box.value = String(friend.id);
      box.addEventListener("change", updateSend);
      var avatar = document.createElement("span");
      avatar.className = "cw-avatar";
      avatar.textContent = friend.initials || "?";
      var copy = document.createElement("span");
      var name = document.createElement("strong");
      name.textContent = friend.name;
      var email = document.createElement("span");
      email.textContent = friend.email;
      copy.appendChild(name);
      copy.appendChild(email);
      row.appendChild(box);
      row.appendChild(avatar);
      row.appendChild(copy);
      list.appendChild(row);
    });
    empty.hidden = friends.length !== 0;
    list.hidden = friends.length === 0;
    search.hidden = friends.length <= 6;
    sendButton.hidden = friends.length === 0;
    updateSend();
    if (shown === 0 && friends.length) {
      empty.hidden = true;
    }
  }

  opener.addEventListener("click", function () {
    picker.hidden = false;
    fetch(opener.getAttribute("data-picker"), { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        friends = Array.isArray(data) ? data : [];
        if (search) {
          search.value = "";
        }
        render("");
      })
      .catch(function () {
        toast("Could not load friends.", true);
      });
  });

  if (search) {
    search.addEventListener("input", function () {
      render(search.value);
    });
  }

  sendButton.addEventListener("click", function () {
    var ids = selectedIds();
    if (!ids.length || sendButton.getAttribute("aria-busy") === "true") {
      return;
    }
    var body = "csrf_token=" + encodeURIComponent(csrf())
      + "&book_format=" + encodeURIComponent(opener.getAttribute("data-format") || "")
      + "&convert=" + encodeURIComponent(opener.getAttribute("data-convert") || "0");
    ids.forEach(function (id) {
      body += "&friend_id=" + encodeURIComponent(id);
    });
    sendButton.disabled = true;
    sendButton.setAttribute("aria-busy", "true");
    sendButton.textContent = "Sending";
    post(opener.getAttribute("data-send"), body).then(function (data) {
      sendButton.removeAttribute("aria-busy");
      updateSend();
      if (!data._ok || !data.ok) {
        toast(data.message || "Could not send this book.", true);
        return;
      }
      picker.hidden = true;
      toast(data.message || "Sent");
    }).catch(function () {
      sendButton.removeAttribute("aria-busy");
      updateSend();
      toast("Could not send this book.", true);
    });
  });

  picker.addEventListener("click", function (event) {
    if (event.target === picker || event.target.closest("[data-close='picker']")) {
      picker.hidden = true;
    }
  });
})();

(function () {
  document.querySelectorAll(".cw-toast").forEach(function (toast) {
    function dismiss() {
      toast.remove();
    }
    var close = toast.querySelector(".cw-toast-close");
    if (close) {
      close.addEventListener("click", dismiss);
    }
    window.setTimeout(dismiss, 3000);
  });

  var nav = document.querySelector(".cw-nav");
  var openSearch = document.getElementById("cw-search-open");
  var closeSearch = document.getElementById("cw-search-close");
  var query = document.getElementById("query");

  function setSearch(on) {
    if (!nav) {
      return;
    }
    nav.classList.toggle("is-searching", on);
    if (on && query) {
      query.focus();
    }
  }

  if (openSearch) {
    openSearch.addEventListener("click", function () {
      setSearch(true);
    });
  }
  if (closeSearch) {
    closeSearch.addEventListener("click", function () {
      setSearch(false);
    });
  }
})();

(function () {
  var root = document.querySelector(".cw-feature-quote");
  if (!root) {
    return;
  }
  var stage = root.querySelector(".cw-feature-stage");
  var slides = Array.prototype.slice.call(root.querySelectorAll(".cw-feature-slide"));
  var dots = Array.prototype.slice.call(root.querySelectorAll(".cw-feature-dot"));
  var next = root.querySelector(".cw-feature-next");
  if (!stage || slides.length < 2) {
    return;
  }
  var index = 0;

  function fit() {
    var height = 0;
    slides.forEach(function (slide) {
      var previous = slide.style.position;
      var hidden = slide.style.visibility;
      slide.style.position = "relative";
      slide.style.visibility = "hidden";
      height = Math.max(height, slide.offsetHeight);
      slide.style.position = previous;
      slide.style.visibility = hidden;
    });
    if (height) {
      stage.style.height = height + "px";
    }
  }

  function show(nextIndex) {
    index = (nextIndex + slides.length) % slides.length;
    slides.forEach(function (slide, slideIndex) {
      slide.classList.toggle("is-active", slideIndex === index);
    });
    dots.forEach(function (dot, dotIndex) {
      dot.classList.toggle("is-active", dotIndex === index);
    });
  }

  if (next) {
    next.addEventListener("click", function () {
      show(index + 1);
    });
  }
  dots.forEach(function (dot, dotIndex) {
    dot.addEventListener("click", function () {
      show(dotIndex);
    });
  });
  fit();
  window.addEventListener("resize", fit);
})();

document.querySelectorAll(".cw-review-more").forEach(function (button) {
  button.addEventListener("click", function () {
    var section = button.closest(".cw-reader-reviews");
    if (!section) return;
    section.classList.add("is-open");
    button.hidden = true;
  });
});

document.querySelectorAll(".cw-blurb-more").forEach(function (button) {
  button.addEventListener("click", function () {
    var rest = button.parentElement.querySelector(".cw-hero-blurb-rest");
    if (!rest) {
      return;
    }
    var open = rest.hidden;
    rest.hidden = !open;
    button.textContent = open ? "Show less" : "Read more";
  });
});

document.querySelectorAll(".cw-hero-quotes").forEach(function (root) {
  var slides = Array.prototype.slice.call(root.querySelectorAll(".cw-hero-quote"));
  var dots = Array.prototype.slice.call(root.querySelectorAll(".cw-hero-dot"));
  if (slides.length < 2) {
    return;
  }
  var index = 0;
  var timer = 0;
  var narrow = window.matchMedia("(max-width: 800px)").matches;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function show(next) {
    index = (next + slides.length) % slides.length;
    slides.forEach(function (slide, slideIndex) {
      slide.classList.toggle("is-active", slideIndex === index);
    });
    dots.forEach(function (dot, dotIndex) {
      dot.classList.toggle("is-active", dotIndex === index);
    });
  }

  function start() {
    if (narrow || reduce) {
      return;
    }
    stop();
    timer = window.setInterval(function () {
      show(index + 1);
    }, 8000);
  }

  function stop() {
    if (timer) {
      window.clearInterval(timer);
      timer = 0;
    }
  }

  dots.forEach(function (dot, dotIndex) {
    dot.addEventListener("click", function () {
      show(dotIndex);
      start();
    });
  });
  root.addEventListener("mouseenter", stop);
  root.addEventListener("mouseleave", start);
  start();
});
