# names.py

class IntervalIds:
    FILE_REFRESH = "interval-file-refresh"


class StoreIds:
    DATA = "store-data"


class TextIds:
    STATUS = "status-text"


class MapIds:
    GRAPH = "map-graph"


class ControlIds:
    REFRESH_BTN_ID = "refresh-files"
    GLIDER_CHECKLIST = "glider-checklist"
    MAP_COLOR_RADIO = "map-color-radio"
    LAYERS_RADIO = "layers-radio"
    CAST_DIR_RADIO = "cast-direction-radio"
    MAP_OPTIONS_RADIO = "map-options-radio"
    TIME_RANGE = "time-range-slider"


class InstrumentsIds:
    TAB_VALUE = "tab-instruments"

    IV_RADIO = "instruments-iv-radio"          # Independent variable: time / depth
    DV_DROPDOWN = "instruments-dv-dropdown"    # Dependent variables (multi)
    PHASE_RADIO = "instruments-phase-radio"    # Phase filter
    PLOTS = "instruments-plots"                # Container for plots


class TabsIds:
    TABS = "main-tabs"
    CONTENT = "tabs-content"
    INSTRUMENTS_TAB_VALUE = InstrumentsIds.TAB_VALUE




