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
})();
