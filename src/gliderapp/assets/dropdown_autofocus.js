// dcc.Dropdown 4.0 (Radix popover) auto-focuses the search input only when
// no value is selected. With a value preselected, focus lands on the selected
// option instead. Force focus into the search input on every dropdown click.
//
// version: 3
(function () {
    function focusSearch() {
        var inputs = document.querySelectorAll('input.dash-dropdown-search');
        for (var i = 0; i < inputs.length; i++) {
            var inp = inputs[i];
            if (inp.offsetParent !== null && document.activeElement !== inp) {
                inp.focus();
                return true;
            }
        }
        return false;
    }

    document.addEventListener('mousedown', function () {
        setTimeout(focusSearch, 0);
        setTimeout(focusSearch, 30);
        setTimeout(focusSearch, 100);
        setTimeout(focusSearch, 250);
    }, true);
})();
