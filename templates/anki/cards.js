/* Acervo cards: dress each recording as a player, and play the word on a listening card.

   A field holds a plain HTML audio element naming its file, which is what Anki's Check Media
   recognises as a reference. Anki's own sound tag would bring Anki's own button, which cannot be
   styled the same in every client. Never write that tag here, not even in a comment: Anki finds it
   anywhere in a card, and every card would then ask to play a file that does not exist. Anki runs a
   card's scripts again for every card it shows, sometimes into the same page, so this marks what it
   has done and does nothing twice. */
(function () {
  var PLAY = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M0 0l10 5-10 5z"/></svg>';
  var BARS = [40, 70, 55, 95, 60, 85, 45, 75, 50, 30, 60, 35];

  function stopOthers(except) {
    var playing = document.querySelectorAll(".acv audio");
    for (var i = 0; i < playing.length; i++) {
      if (playing[i] !== except && !playing[i].paused) { playing[i].pause(); playing[i].currentTime = 0; }
    }
  }

  function play(audio) {
    stopOthers(audio);
    audio.currentTime = 0;
    var started = audio.play();
    if (started && started.catch) started.catch(function () {});
  }

  function follow(audio, control) {
    audio.addEventListener("play", function () { control.classList.add("playing"); });
    audio.addEventListener("pause", function () { control.classList.remove("playing"); });
    audio.addEventListener("ended", function () { control.classList.remove("playing"); });
  }

  function dress(audio) {
    if (audio.getAttribute("data-acv")) return;
    audio.setAttribute("data-acv", "1");
    audio.preload = "auto";
    var mini = !!audio.closest(".def, .src");
    var button = document.createElement("button");
    button.type = "button";
    button.className = mini ? "audio mini" : "audio";
    button.setAttribute("aria-label", "Play");
    button.innerHTML = '<span class="pi">' + PLAY + "</span>" + (mini ? "" :
      '<span class="wave">' + BARS.map(function (h) { return '<i style="height:' + h + '%"></i>'; }).join("") + "</span>");
    button.addEventListener("click", function (event) {
      event.stopPropagation();
      if (audio.paused) play(audio); else audio.pause();
    });
    follow(audio, button);
    audio.parentNode.insertBefore(button, audio);
  }

  var sounds = document.querySelectorAll(".acv audio");
  for (var i = 0; i < sounds.length; i++) {
    if (!sounds[i].closest(".listen-stage")) dress(sounds[i]);
  }

  // A listening card: the big button plays the word, and the card tries once to play it by itself.
  // A client that refuses autoplay leaves the button to be pressed.
  var stage = document.querySelector(".listen-stage:not([data-acv])");
  if (stage) {
    stage.setAttribute("data-acv", "1");
    var word = stage.querySelector("audio");
    var big = stage.querySelector(".play-big");
    if (word && big) {
      follow(word, big);
      big.addEventListener("click", function (event) { event.stopPropagation(); play(word); });
      play(word);
    }
  }
})();
