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
})();
