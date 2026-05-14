// On any click, find the nearest ancestor that contains a react-select
// search input and focus that input. Works whether or not a value is selected.
(function () {
    document.addEventListener('mousedown', function (e) {
        var node = e.target;
        while (node && node !== document.body) {
            var inp = node.querySelector
                ? node.querySelector('input[role="combobox"]')
                : null;
            if (inp) {
                setTimeout(function () { inp.focus(); }, 0);
                setTimeout(function () { inp.focus(); }, 50);
                return;
            }
            node = node.parentNode;
        }
    }, true);
})();
