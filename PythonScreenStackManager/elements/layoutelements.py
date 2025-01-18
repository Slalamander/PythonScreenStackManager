"""
Elements that can be used to arrange other elements
"""

from math import floor, ceil
import asyncio

from PIL.Image import Image
from typing import Coroutine, Sequence
from types import MappingProxyType

from ..exceptions import *
from . import baseelements as base
from . import compoundelements as comps     ##May need restructuring here if I want to use compounds with grid elements -> Nope probably? Since that would kinda take away some configuration
from .baseelements import Element, elementactionwrapper, elementaction, colorproperty, trigger_condition
from .constants import DEFAULT_ACCENT_COLOR, DEFAULT_BACKGROUND_COLOR, DEFAULT_FOREGROUND_COLOR
from ..pssm_types import *
from .. import tools

_LOGGER = base._LOGGER

class _GridElement(base.Element):
    """
    Helper Element for elements that are embedded in Grid Layouts. Used to give them the `grid_row` and `grid_column` attributes with functionality to update the parent GridLayout.
    """    

    @property
    def grid_row(self) -> Optional[int]:
        "The row this element will be located on"
        return self._grid_row
    
    @grid_row.setter
    def grid_row(self, value):
        if value != None and not isinstance(value, int):
            _LOGGER.warning(f"{self}: grid_row must be None or a positive integer")
            return
        
        if value == None:
            pass
        elif value < 1:
            _LOGGER.warning(f"{self}: grid_row must be at least 1")
            return
        
        self._grid_row = value

        if isinstance(self.parentLayout,GridLayout):
            self.parentLayout._rebuild_layout = True
            self.parentLayout.update(updated=True)

    @property
    def grid_column(self) -> Optional[int]:
        "The row this element will be located on"
        return self._grid_column
    
    @grid_column.setter
    def grid_column(self, value):
        if value != None and not isinstance(value, int):
            _LOGGER.warning(f"{self}: grid_column must be None or a positive integer")
            return
        
        if value == None:
            pass
        elif value < 1:
            _LOGGER.warning(f"{self}: grid_column must be at least 1")
            return
        
        self._grid_column = value
        if isinstance(self.parentLayout,GridLayout):
            self.parentLayout._rebuild_layout = True
            self.parentLayout.update(updated=True)

    @classmethod
    def wrap_element(cls, element):
        "Applies the grid_row and grid_column attributes (and their functionality) to the provided element, in place."
            
        elt = element
        properties = {"grid_row": getattr(elt, "grid_row",None), "grid_column": getattr(elt, "grid_column",None)}
        grid_class = type(elt.__class__.__name__,(elt.__class__,_GridElement),{}) ##Don't need to update the typeDict, since the properties are taken over by adding the GridElement as a base
        elt.__class__ = grid_class
        for prop, val in properties.items():
            setattr(elt,prop, val)

class GridLayout(base.Layout):
    """
    A Layout element that allows for easy placement of elements within a grid.
    Elements that are added to it (either at initialisation or via `GridLayout.add_elements`) will be given a `grid_row` and `grid_column` attribute with functionality to notify the GridLayout that their position changed.
    Elements do not need a value for `grid_row` and `grid_column`, in which case the GridLayout will attempt to place them later on in the leftover empty cells.
    Any elements that overflow the available number of grid cells, or have their `grid_row` and `grid_column` overlap with that of another Element will not be put in the Layout, but will be saved for new iterations of the GridLayout in case space becomes available.
    `rows` or `columns` can be set to `None`, in which case they will be set as needed by the number of elements. However, it is not allowed to set both to `None`.

    Parameters
    ----------
    elements : list[base.Element]
        The elements to add to the grid.
        Can be assigned a location by setting `grid_row` and `grid_column` (Keep in mind indices start at 0)
    rows : int, optional
        The number of rows, by default 4
        If None, the rows will be set depending on the number of elements
    columns : int, optional
        The number of columns, by default 4
        If None, the columns will be set depending on the number of elements
    row_sizes : list[PSSMdimension], optional
        The sizes (heights) of the rows, by default "?"
        If a single value, all rows will be assigned that size. 
        If a list, the row sizes will be matched to their respective index in the list, with any rows outside of it being given a "?" size. (So, passing value `[50,75]` will mean row 1 has height 50px and row 2 has height 75px. Any rows after that will have their size set to fill in the remaining space.)
    column_sizes : list[PSSMdimension], optional
        Sizes (width) of the columns, by default "?"
        Has the same functionality as `row_sizes`
    outer_margins : list[PSSMdimension], optional
        The sizes of the outer margins of the grid, by default 0
        Values can are parsed as CSS margins, i.e. passing 2 values will assign the first value to the top and bottom margin and the second value to the left and right margin.
    inner_margins : list[PSSMdimension], optional
        The sizes of the inner margins of the grid,, by default 0
        Like `outer_margins`, values are parsed as CSS grids.
    """

    @property
    def _emulator_icon(cls): return "mdi:dots-grid"
    
    def __init__(self, elements : Sequence[base.Element], rows : int = 4, columns : int = 4,
                row_sizes : list[PSSMdimension] = "?", column_sizes : list[PSSMdimension] = "?",
                outer_margins : list[PSSMdimension] = 0, inner_margins : list[PSSMdimension] = 0, **kwargs):

        self.rows = rows
        self.row_sizes = row_sizes
        
        self.columns = columns
        self.column_sizes = column_sizes
        
        self.outer_margins = outer_margins
        self.inner_margins = inner_margins

        super().__init__(None, **kwargs)

        if any([isinstance(x,(str,dict,MappingProxyType)) for x in elements]):
            self.__element_strings = []
            self.screen._add_element_attribute_check(self,"__element_strings",self.__parse_string_elements)

        self.__elements = []
        self.add_elements(*elements)

        self.build_layout()

    #region
    @property
    def elements(self) -> tuple[_GridElement]:
        "The list of elements assigned to this grid"
        return tuple(self.__elements)

    @property
    def outer_margins(self) -> tuple[PSSMdimension,PSSMdimension,PSSMdimension,PSSMdimension]:
        "The values of the outer margins, parsed to a 4 tuple (i.e. the (top,right,bottom,left) margins respectively)"
        return self.__outer_margins
    
    @outer_margins.setter
    def outer_margins(self, value : Union[PSSMdimension, list[PSSMdimension]]):
        ##Don't forget inner/outer margins
        if not isinstance(value, (list,tuple)):
            value = [value]
        else:
            value = list(value)
        
        l = len(value)
        if not 1 <= l <= 4:
            msg = f"{self}: margins cannot be set to {value}, value must be a single dimension, or a list of 1 to 4 dimensions"
            _LOGGER.exception(msg)

        for m in value.copy():
            res = tools.is_valid_dimension(m)
            if isinstance(res, Exception):
                _LOGGER.exception(res)
                return

        l = len(value)
        if l == 4:
            pass
        elif l == 3:
            value.append(value[1])
        elif l == 2:
            value.extend(value)
        elif l == 1:
            value = [value[0]]*4    

        self.__outer_margins = tuple(value)
        self._rebuild_layout = True
    
    @property
    def inner_margins(self) -> tuple[PSSMdimension,PSSMdimension,PSSMdimension,PSSMdimension]:
        "The values of the inner margins, parsed to a 4 tuple (i.e. the (top,right,bottom,left) margins respectively)"
        return self.__inner_margins
    
    @inner_margins.setter
    def inner_margins(self, value : Union[PSSMdimension, list[PSSMdimension]]):
        ##Don't forget inner/outer margins
        if not isinstance(value, (list,tuple)):
            value = [value]
        else:
            value = list(value)
        
        l = len(value)
        if not 1 <= l <= 4:
            msg = f"{self}: margins cannot be set to {value}, value must be a single dimension, or a list of 1 to 4 dimensions"
            _LOGGER.exception(msg)

        for m in value.copy():
            res = tools.is_valid_dimension(m)
            if isinstance(res, Exception):
                _LOGGER.exception(res)
                return

        l = len(value)
        if l == 4:
            pass
        elif l == 3:
            value.append(value[1])
        elif l == 2:
            value.extend(value)
        elif l == 1:
            value = [value[0]]*4    

        self.__inner_margins = tuple(value)
        self._rebuild_layout = True

    @property
    def rows(self) -> Optional[int]:
        "The number of rows in the grid. If None, rows will be set as needed, provided columns is not None"
        return self._rows
    
    @rows.setter
    def rows(self, value):
        if value != None and not isinstance(value,int):
            msg = f"{self}: rows must be either None or an integer. Value {value} with type {type(value)} is not valid"
            _LOGGER.exception(TypeError(msg))
            return
        self._rows = value

    @property
    def row_sizes(self) -> list[PSSMdimension]:
        "Sizes of the rows. Either a list with the values of the corresponding row index, or a single value with the size for all rows"
        if isinstance(self._row_sizes, list):
            return self._row_sizes.copy()
        return self._row_sizes
    
    @row_sizes.setter
    def row_sizes(self, value):
        self._row_sizes = value
        self._rebuild_layout = True

    @property
    def columns(self) -> Optional[int]:
        "The number of columns in the grid. If None, columns will be set as needed, provided rows is not None"
        return self._columns
    
    @columns.setter
    def columns(self, value):
        if value != None and not isinstance(value,int):
            msg = f"{self}: columns must be either None or an integer. Value {value} with type {type(value)} is not valid"
            _LOGGER.exception(TypeError(msg))
            return
        self._columns = value

    @property
    def column_sizes(self) -> list[PSSMdimension]:
        "Sizes of the columns. Either a list with the values of the corresponding column index, or a single value with the size for all columns"
        if isinstance(self._column_sizes, list):
            return self._column_sizes.copy()
        return self._column_sizes
    
    @column_sizes.setter
    def column_sizes(self, value):
        self._column_sizes = value
        self._rebuild_layout = True
    #endregion

    def add_elements(self, *elements : base.Element):
        """
        Add elements to this GridLayout.

        Paramaters
        ----------
        elements : args
            The new elements to add. Any element that does not have it yet, will be given the `grid_row` and `grid_column` attributes
            Can be passed as a string, or a dict with element_id, which will have the Grid get the element from the element register.
        """        
        for elt in elements:
            if isinstance(elt,(str,dict,MappingProxyType)):
                if isinstance(elt,(dict,MappingProxyType)):
                    if "element_id" not in elt:
                        _LOGGER.exception(f"{self}: Passing an element as a dict to a GridLayout requires the 'element_id' key")
                        continue
                    elt = elt["element_id"]

                if elt in self.screen.elementRegister:
                    elt = elt = self.screen.elementRegister[elt]
                elif not self.screen.printing:
                    self.__element_strings.append(elt)
                    continue
                else:
                    msg = f"No element with element id {elt} is registered."
                    _LOGGER.exception(msg)
                    continue

            if elt in self.__elements:
                _LOGGER.warning(f"Element {elt} is already in grid {self}")
                continue

            if not isinstance(elt, _GridElement) and isinstance(elt, Element):
                _GridElement.wrap_element(elt)

            self.__elements.append(elt)
        self._rebuild_layout = True

    def remove_elements(self, *elements):
        "Removes the provided elements from the grid's element list"
        
        for elt in elements:
            if elt in self.__elements: self.__elements.remove(elt)
        self._rebuild_layout = True

    def __parse_string_elements(self, *args):
        "This function parses any element_id strings added as elements before printing."

        elt_list = []
        for elt_str in self.__element_strings:
            if elt_str not in self.screen.elementRegister:
                msg = f"No element with element id {elt_str} is registered."
                _LOGGER.exception(msg)
                continue
            else:
                elt = self.screen.elementRegister[elt_str]
                elt_list.append(elt)
                if not isinstance(elt, _GridElement):
                    _GridElement.wrap_element(elt)
                elt_idx = self.__elements.index(elt_str)
                self.__elements[elt_idx] = elt
        self._rebuild_layout = True
        
    def create_element_grid(self):
        "Creates a the grid with the indices for all elements, or None when out of elements. Margins are not yet included."
        
        num_columns = self.columns
        num_rows = self.rows
        
        if num_columns == num_rows == None:
            msg = f"{self}: number of rows and number of columns cannot both be 0!"
            _LOGGER.exception(ValueError(msg))
            return
        
        if num_columns == None or num_rows == None:
            if num_rows == None: mult = self.columns
            if num_columns == None: mult = self.rows

            min_cells = max(len(self.elements),1)

            c = ceil(min_cells/mult)

            if num_rows == None: num_rows = c
            if num_columns == None: num_columns = c

        grid_columns = [None]*num_columns
        grid = [grid_columns.copy() for i in range(num_rows)]

        assign_later = []
        for elt in self.elements:
            if getattr(elt,"grid_row",None) == None and getattr(elt,"grid_column",None) == None:
                assign_later.append(elt)
                continue

            if elt.grid_row >= num_rows or elt.grid_column >= num_columns:
                _LOGGER.warning(f"{self}: {elt} has grid position ({elt.grid_column+1},{elt.grid_row+1}) (grid_column {elt.grid_column}, grid_row {elt.grid_row}), but exeeds grid size of ({num_columns},{num_rows})")    
                assign_later.append(elt)
                continue
            
            grid_fill = grid[elt.grid_row][elt.grid_column]
            if grid_fill != None:
                _LOGGER.warning(f"{self}: {elt} has grid position ({elt.grid_column},{elt.grid_row}), but it is already assigned to element {grid_fill}")    
                assign_later.append(elt)
                continue

            grid[elt.grid_row][elt.grid_column] = elt

        if not assign_later:
            return grid
        
        for i,row in enumerate(grid):
            for j, col in enumerate(row):
                if col != None:
                    continue

                grid[i][j] = assign_later.pop(0)

                if not assign_later:
                    break

            if not assign_later:
                break
                
        if assign_later:
            msg = f"{self}: made a grid, but not all elements fitted. {assign_later} are omitted."
            _LOGGER.warning(msg)

        return grid

    def build_layout(self):
        "Builds the grid layout"
        elt_grid = self.create_element_grid()
        outer_margins = self.outer_margins
        inner_margins = self.inner_margins


        num_columns = self.columns
        num_rows = self.rows
        if num_columns == None or num_rows == None:
            if num_rows == None: mult = self.columns
            if num_columns == None: mult = self.rows

            min_cells = max(len(self.elements),1)

            c = ceil(min_cells/mult)

            if num_rows == None: num_rows = c
            if num_columns == None: num_columns = c

        row_sizes = self.row_sizes
        if not isinstance(row_sizes,list):
            row_sizes = [row_sizes]*num_rows
        elif len(row_sizes) < num_rows:
            row_sizes.extend(["?"] * (num_rows - len(row_sizes)))

        col_sizes = self.column_sizes
        if not isinstance(col_sizes,list):
            col_sizes = [col_sizes]*num_columns
        elif len(col_sizes) < num_columns:
            col_sizes.extend(["?"] * (num_columns - len(col_sizes)))

        layout = []
        if outer_margins[0] != 0:
            layout.append([outer_margins[0]])

        for i, grid_row in enumerate(elt_grid):
            if inner_margins[0] != 0:
                layout.append([inner_margins[0]])

            row = [row_sizes[i]]
            if (m := outer_margins[3]) != 0:
                row.append((None,m))

            for j, elt in enumerate(grid_row):
                if (m := inner_margins[3]) != 0:
                    row.append((None,m))

                row.append((elt,col_sizes[j]))

                if (m := inner_margins[1]) != 0:
                    row.append((None,m))

            if (m := outer_margins[1]) != 0:
                row.append((None,m))
            layout.append(row)

            if inner_margins[2] != 0:
                layout.append([inner_margins[2]])
        
        if outer_margins[2] != 0:
            layout.append([outer_margins[0]])
        
        self.layout = layout
        self._rebuild_layout = False
        self._rebuild_area_matrix = True

    def generator(self, area=None, skipNonLayoutGen=False):
        if self._rebuild_layout:
            self.build_layout()
            
        img = super().generator(area, skipNonLayoutGen)
        return img
    
    async def async_generate(self, area=None, skipNonLayoutGen: bool = False) -> Coroutine[Any, Any, Coroutine[Any, Any, Image]]:
        async with self._generatorLock:
            if self._rebuild_layout:
                self.build_layout()
        return await super().async_generate(area, skipNonLayoutGen)

class NavigationTile(base.TileElement):
    """
    Styled Tile Element to use with the TabPages. Used to show and select the tabs.
    Not quite fully developed since it's not meant to be used as a standalone element.
    Comes with the special tile_layout 'auto', which means it sets its layout base on the layout of the parent TabPages Element.

    Parameters
    ----------
    tile_layout : str
        Layout of the navigation Tile. Generally passed as 'auto'
    icon : mdiType
        Icon to use for this tile
    name : str
        The name of this Tile, shows as the text.
    """

    @classproperty
    def tiles(cls):
        return ("icon","name","line")

    @property
    def _emulator_icon(cls): return "mdi:navigation-variant"

    def __init__(self, tile_layout : str, icon : mdiType, name : str, **kwargs): 
        NavIcon = base.Icon(icon, background_shape="circle", _isNavElt=True, NavTile = self)
        if icon == None:
            NavIcon._icon = None
        NavText = base.Button(name, text_x_position="left", fit_text=True, _isNavElt=True, NavTile = self)
        NavLine = base.Line(line_color=None, width=4, alignment="top", _isNavElt=True, NavTile = self)

        self.__elements = {"icon": NavIcon, "name": NavText, "line": NavLine}
        super().__init__(tile_layout,**kwargs)
        self._reparse_layout = True
    
    @property
    def elements(self) -> dict[Literal["icon","name","line"],Union[base.Icon,base.Button,base.Line]]:
        return self.__elements

    @property
    def tile_layout(self) -> PSSMLayoutString:
        if self._tile_layout == "auto":
            l = self.get_auto_layout()
            return l
            ##Let the parentTab return the layout
            ##And also set the properties appropriately
            ##tab tile_layout setter: go through the tiles and set the lines etc. if _tile_layout is auto
        return base.TileLayout.tile_layout.fget(self)
    
    @tile_layout.setter
    def tile_layout(self, value: str):
        if value.lower() == "auto":
            self._tile_layout = "auto"
        base.TileLayout.tile_layout.fset(self, value)

    def get_auto_layout(self) -> PSSMLayoutString:
        "Returns the default layout as per the `TabPages` element this `NavigationTile` is contained in."
        if not self.onScreen or self.parentLayout == None or len(self.parentLayouts) < 2:
            return "[icon,name];line"

        tabparent : TabPages = self.parentLayouts[-2]
        parent_layout = tabparent._tile_layout

        if parent_layout not in TabPages.defaultLayouts or parent_layout in {"top", "bottom"}:
            return "[icon,name];line"
        elif parent_layout == "left":
            return "line,icon"
        elif parent_layout == "right":
            return "icon,line"

    def update(self, updateAttributes={}, skipGen=False, forceGen: bool = False, skipPrint=False, reprintOnTop=False, updated: bool = False):
        return super().update(updateAttributes, skipGen, forceGen, skipPrint, reprintOnTop, updated)
    
    async def async_update(self, updateAttributes=..., skipGen=False, forceGen = False, skipPrint=False, reprintOnTop=False, updated = False):
        upd = await super().async_update(updateAttributes, skipGen=True)
        await asyncio.sleep(0)
        await super().async_update({}, skipGen, forceGen, skipPrint, reprintOnTop, updated=updated or upd)
        return upd

    async def async_generate(self, area=None, skipNonLayoutGen=False):
        await asyncio.sleep(0)
        return await super().async_generate(area, skipNonLayoutGen)

    def generator(self, area=None, skipNonLayoutGen=False):
        img = super().generator(area, skipNonLayoutGen)
        return img

##Kinda want to keep them called Pages cause of Ereader shenanigans
##In a way you'd page through things anyways

class tabDict(TypedDict):
    "Options for a tab page in the TabPages element"

    element : Element
    "The element to add as a tab"

    name : str
    "The name of this tab. Must be unique within the TabPages Element"

    icon : Union[str, mdiType]
    "Optional icon to represent this tab with"

    index : int
    "Optional index (page number) that will be given to this tab"


class TabPages(base.TileElement):
    """A layout that can hold multiple other elements (as tabs). 

    Comes with elements to cycle through the tab list, as well as a navigation bar that can be used to go to a specific tab.
    Generally, when referring to a page, an index (page number) is required. When referring to a tab, the tab name is required.
    The hide property has been restricted, and hiding the tab element is not permitted. Use `hide_navigation_bar` and `hide_page_handles` instead.
    Each entry in the navigation bar is made using a :py:class:`NavigationTile`
    
    Parameters
    ----------
    tabs : list[tabDict]
        The tabs to register. By default, page indices will be set in order of the elements.
        Every dict requires at least an element and the tab name to be present. Can also be given an icon, to specify which icon to use for this tab.
    tile_layout : Union[Literal[&quot;top&quot;,&quot;bottom&quot;,&quot;left&quot;,&quot;right&quot;], PSSMLayoutString], optional
        The layout of this tab element, by default "bottom"
        Generally, using the default layouts is recommended.
    apply_default_sizes : bool, optional
        When using one of the default layouts, this will automatically size the elements to fit well, by default True
    navigation_tile_size : Union[float,PSSMdimension], optional
        The size of a navigation tile, by default 0.2
        A float smaller than 0 will be used to set the fraction of width/height of the Navigation Bar depending on the orientation of it.
    hide_navigation_bar : bool, optional
        Hides the navigation bar that shows Tile elements to quickly switch to a specific tab, by default False
    hide_page_handles : bool, optional
        Hides the handles that can be used to go to the next/previous page, by default True
    cycle : bool, optional
        When using the page handles, or calling `next_page` or `previous_page`, if this is True, this will mean the element will loop through tabs. Otherwise, it won't change the current tab if the list is exhausted.
        , by default True
    element_properties : dict, optional
        Optional element properties to apply, by default {}
        Applied properties include the icon and icon_color of the page handles, and the styling of the navigation bar.
        For the latter, this means setting the active_color to the foreground_color of the `TabPages` and inactive to None, with line color and icon background_color being changed appropriately.
    """        
    
    defaultLayouts = {"top": "navigation;[handle-previous,tab,handle-next]",
                        "bottom": "[handle-previous,tab,handle-next];navigation",
                        "left": "navigation,[tab;[handle-previous,handle-next]]",
                        "right": "[tab;[handle-previous,handle-next]],navigation"
                        }

    _restricted_element_properties : dict[str,set[str]] = {"navigation": {"allow_deselect", "tap_action"}, "handle-next" : {"tap_action"}, "handle-previous" : {"tap_action"}}
    "Properties of the elements that are not allowed to be set."

    @property
    def _emulator_icon(cls): return "mdi:page-layout-sidebar-left"

    @classproperty
    def action_shorthands(cls) -> dict[str,Callable[["base.Element", CoordType],Any]]:
        "Shorthand values mapping to element specific functions. Use by setting the function string as element:{function}"
        return base.TileElement.action_shorthands | {"show-page": "show_page_shorthand", "show-tab": "show_tab_shorthand", "next-page": "next_page", "previous-page": "previous_page"}

    @classproperty
    def tiles(cls) -> tuple[str,str,str,str]:
        return ("navigation", "handle-next", "handle-previous", "tab")

    def __init__(self, tabs : list[tabDict], tile_layout : Union[Literal["top","bottom","left","right"], PSSMLayoutString] = "bottom",
                apply_default_sizes : bool = True, navigation_tile_size : Union[float,PSSMdimension] = 0.2,
                hide_navigation_bar : bool = False, hide_page_handles : bool = True, cycle : bool = True,
                element_properties : dict = {}, horizontal_sizes: dict[str,PSSMdimension] = {}, vertical_sizes: dict[str,PSSMdimension] = {},
                **kwargs) -> None:

        BackHandle = base.Icon("mdi:menu-left", icon_color='foreground', tap_action = self.previous_page)
        NextHandle = base.Icon("mdi:menu-right", icon_color='foreground', tap_action = self.next_page)

        self.__NavBar : Union[base._ElementSelect, GridLayout] = GridLayout(rows=1,columns=None, elements=[], column_sizes="w*0.2",
                                                                            outer_margins=[0,"?",0,"w*0.025"])

        self.__NavBar : base._ElementSelect

        base._ElementSelect(self.__NavBar, {}, allow_deselect=False, active_color="foreground", inactive_color=None,
                            active_properties={"accent_color": "active","element_properties": {"line": {"line_color": "active"}, "icon": {"background_color": "active"}}}, 
                            inactive_properties={"accent_color": "inactive", "element_properties": {"line": {"line_color": "inactive"}, "icon": {"background_color":  "inactive", "icon_color": "gray"}}})

        self.__NavBar.on_select = self._navigation_show_tab

        self.__elements = {"handle-previous": BackHandle, "handle-next": NextHandle, "navigation": self.__NavBar}

        self.__tabElements = []
        self.__tabNames = []
        self.__tabs = {}

        for tab in tabs:
            self.add_tab(**tab)

        self.__currentTab = None
        self._currentIdx = None
        self.__NavBar.selected
        self.__NavBar.select(self.__tabNames[0])

        self.apply_default_sizes = apply_default_sizes
        self.hide_navigation_bar = hide_navigation_bar
        self.hide_page_handles = hide_page_handles

        self.cycle = cycle
        self.navigation_tile_size = navigation_tile_size

        vertical_sizes = vertical_sizes
        horizontal_sizes = horizontal_sizes

        super().__init__(tile_layout, vertical_sizes=vertical_sizes, horizontal_sizes=horizontal_sizes, element_properties=element_properties, **kwargs)

        self._set_default_sizes()

    #region
    @property
    def elements(self) -> dict[Literal["navigation","handle-previous","handle-next","tab"], Union[base.Layout,GridLayout, base.Icon]]:
        return self.__elements | {"tab": self.__currentTab}

    @base.TileElement.tile_layout.setter
    def tile_layout(self, value):
        if value == getattr(self,"_tile_layout",None):
            return
        
        base.TileElement.tile_layout.fset(self, value)
        if self._tile_layout != value or value not in TabPages.defaultLayouts:
            return ##This means something was wrong with the layout (or it's not a default one)

        self._resize_defaults = True

    @property
    def tabs(self) -> dict:
        "The dict with tab names and their config"
        return MappingProxyType(self.__tabs)

    @property
    def currentTab(self) -> Element:
        "Returns the current Tab page that is showing"
        return self.__currentTab

    @property
    def currentPage(self) -> str:
        "The name of the current page being shown"
        if self._currentIdx != None:
            return self.__tabNames[self._currentIdx]
        else:
            return None

    @property
    def pageElements(self) -> tuple:
        "Tuple with the registered tabs, in order"
        return tuple(self.__tabElements)
    
    @property
    def pageNames(self) -> tuple:
        "Tuple with the names of all registered tabs, in the same order as pageElements"
        return tuple(self.__tabNames)

    @property
    def tabElements(self):
        "Names of tabs linked to their elements"
        d = {}
        for i, name in enumerate(self.pageNames):
            d[name] = self.pageElements[i]
        return MappingProxyType(d)
    
    @property
    def hide(self) -> tuple:
        """
        The elements to hide from this Tab. Cannot be set directly for TabPages, use `hide_navigation_bar` and `hide_page_handles` instead.

        Returns
        -------
        tuple
            The elements in the tile_layout to hide.
        """        
        l = []
        if self.hide_navigation_bar: l.append("navigation")
        if self.hide_page_handles: l.extend(["handle-next","handle-previous"])
        return tuple(l)
    
    @property
    def hide_navigation_bar(self) -> bool:
        return self._hide_navigation_bar

    @hide_navigation_bar.setter
    def hide_navigation_bar(self, value: bool):
        self._hide_navigation_bar = bool(value)
        self._resize_defaults = True 

    @property
    def hide_page_handles(self) -> bool:
        return self._hide_page_handles

    @hide_page_handles.setter
    def hide_page_handles(self, value: bool):
        self._hide_page_handles = bool(value)
        self._resize_defaults = True

    @property
    def apply_default_sizes(self) -> bool:
        "If True, applies default sizes and orientations where needed, _if_ a default layout is used. Can be set to False to take (more) control of the element's layout."
        return self._apply_default_sizes
    
    @apply_default_sizes.setter
    def apply_default_sizes(self, value):
        if bool(value) == getattr(self, "_apply_default_sizes", None):
            return
        
        self._apply_default_sizes = bool(value)
        self._resize_defaults = True        

    @property
    def NavigationBar(self) -> Union[GridLayout, base._ElementSelect]:
        "The GridLayout (wrapped into a selector) holding the Tiles to navigate to tabs"
        return self.__NavBar

    @property
    def navigation_tile_size(self) -> Union[float, PSSMdimension]:
        """
        The relative size to use for the Navigation Tile. 
        Depending on the orientation, this will set the row height for the right and left default layouts, and the column width for the top and bottom layouts.
        If a float smaller than 0 is used, it will be parsed as `h*val` or `w*val`, depending on the above.
        """        
        return self._navigation_tile_size
    
    @navigation_tile_size.setter
    def navigation_tile_size(self, value):
        if value == getattr(self,"_navigation_tile_size",None):
            return
        r = tools.is_valid_dimension(value)
        if isinstance(r,Exception):
            _LOGGER.exception(r)
            return
        self._navigation_tile_size = value

    @property
    def navigation_tile_properties(self):
        """
        Any properties set here are applied to all elements in the NavigationBar. Can be used to alter the style of i.e. the background shape of the icon.
        Set the `active_properties` and `inactive_properties` of the NavigationBar (either via updating it using the TabPages `NavigationBar` property, or updating it by setting element_properties{'navigation': {...}}) to alter how tiles that are active and inactive are displayed
        """
        return {}
    
    @navigation_tile_properties.setter
    def navigation_tile_properties(self, value : dict):
        for tile in self.NavigationBar.elements:
            tile.update(value, skipPrint=self.isUpdating)
        return
    #endregion

    def add_tab(self, element : Union[base.Element, Literal["element_id"]], name : str, icon : Union[mdiType,str] = None, index : int = None):
        """
        Add a new tab to this element

        Parameters
        ----------
        element : Union[base.Element, Literal[&quot;element_id&quot;]]
            The element to use as the tab
        name : str
            The tab's name
        icon : Union[mdiType,str], optional
            Icon to use for the tab, by default None
        index : int, optional
            Optional index for the tab, by default None
            Will insert the tab at the given index into the list.
        """        
        
        if name in self.__tabNames:
            _LOGGER.warning(f"{self}: A tab with name {name} already exists in this element. Not adding it.")
            return
        
        if isinstance(element,str):
            if element in self.parentPSSMScreen.elementRegister:
                element = self.parentPSSMScreen.elementRegister[element]
            elif self.parentPSSMScreen.printing:
                raise ElementNotRegistered(element,self)
            else:
                self.screen._add_element_attribute_check(self,name,self.__validate_string_tabs)

        self.__tabElements.append(element)
        idx = self.__tabElements.index(element)

        issub = True
        NavElement = NavigationTile("auto", icon, name, _isSubLayout=issub)

        self.__NavBar.add_elements(NavElement)
        self.__NavBar.add_option(name, NavElement)

        self.__tabNames.append(name)

        if self.parentPSSMScreen.printing:
            self._set_default_sizes(NavElement)

        self.NavigationBar.update(updated=True)
        self.update(updated=True)
        
        self.__tabs[name] = {"element": element, "name": name, "icon": icon, "index": idx} 

    def __validate_string_tabs(self, elt, tab_name):
        
        tabConf = self.__tabs[tab_name]
        elt_str = tabConf["element"]
        if elt_str not in self.screen.elementRegister:
            raise ElementNotRegistered(elt_str,self)
        else:
            elt = self.screen.elementRegister[elt_str]
            tabConf["element"] = elt
            elt_idx = self.__tabElements.index(elt_str)
            self.__tabElements[elt_idx] = elt

            self.__tabs[tab_name] = tabConf
            return

    @trigger_condition
    async def async_show_page(self, index : int):
        """
        Shows the tab at page index index

        Parameters
        ----------
        index : int
            The index of the tab to show
        """        
        if index == self._currentIdx:
            return
        
        if index < 0:
            index = index + len(self.__tabElements)

        if index >= len(self.__tabElements):
            _LOGGER.warning(f"{self}: Has {len(self.__tabElements)} tabs, and index {index} is out of range (Keep in mind you can use indices start at 0 and go up to (number_of_tabs -1))")
            return
        
        self._currentIdx = index
        self.__currentTab = self.__tabElements[index]
        self._reparse_layout = True
        if self.NavigationBar.selected != self.__tabNames[index]:
            await self.NavigationBar.async_select(self.__tabNames[index])
        await self.async_update(updated=True)

    def show_page(self, index : int):
        """
        Shows the tab at page index index

        Parameters
        ----------
        index : int
            The index of the tab to show
        """           
        if asyncio._get_running_loop() == None:
            self.parentPSSMScreen.mainLoop.create_task(self.async_show_page(index))
        else:
            asyncio.create_task(self.async_show_page(index))

    def show_tab(self, name : str):
        """
        Shows the tab with the provided name

        Parameters
        ----------
        name : str
            The name of the tab to show
        """

        if name == None:
            return

        if name not in self.__tabNames:
            msg = f"{self}: {name} is not the name of a registered tab."
            _LOGGER.warning(msg)
            return 

        tab_idx = self.__tabNames.index(name)
        self.show_page(tab_idx)

    async def _navigation_show_tab(self, elt : comps.Tile, option : str):
        """
        Helper function, connected to the Navigation Bar, shows the correct tab when clicking on it's connected element

        Parameters
        ----------
        elt : comps.Tile
            element that was selected, not used
        option : str
            The option selected via the ElementSelect, equivalent to tab name
        """        

        if option not in self.__tabNames:
            msg = f"{self}: {option} is not the name of a registered tab."
            _LOGGER.warning(msg)
            return 

        tab_idx = self.__tabNames.index(option)
        await self.async_show_page(tab_idx)
        
    @elementactionwrapper.method
    async def show_tab_shorthand(self, name : str):
        """
        Helper function that can be used as an element's tap_action to navigate to tab with the provided name, or other shorthands.
        Can be used by setting it as an element's tap_action, via `{'action' : 'show-tab', 'data': {'name': 'my-tab'}}`
        """        
        if name not in self.__tabNames:
            msg = f"{self}: {name} is not the name of a registered tab."
            _LOGGER.warning(msg)
            return 

        tab_idx = self.__tabNames.index(name)
        await self.async_show_page(tab_idx)
    
    @elementactionwrapper.method
    async def show_page_shorthand(self, index : int):
        "Function that can be used as a tap_action i.e. to show a page with a certain number"
        await self.async_show_page(index)

    @elementactionwrapper.method
    def next_page(self, *args):
        """
        Shows the next tab in the list of tabs. If cycle is not `True` and the last page is currently being shown, will do nothing.
        """        
        new_idx = self._currentIdx + 1
        if new_idx >= len(self.__tabElements):
            if not self.cycle:
                return
            
            new_idx = 0

        self.show_page(new_idx)

    @elementactionwrapper.method
    def previous_page(self, *args):
        """
        Shows the previous tab in the list of tabs. If cycle is not `True` and the first page is currently being shown, will do nothing.
        """   
        new_idx = self._currentIdx - 1

        if new_idx < 0 and not self.cycle:
            return

        self.show_page(new_idx)

    def _set_default_sizes(self, *tiles : NavigationTile):
        """
        Updates the NavigationBar and the navigation tiles to match the default styles for the current tile_layout.
        If `apply_default_sizes` is `False` or the tile_layout is not a default style, will do nothing.
        """
        if not self.apply_default_sizes or self._tile_layout not in TabPages.defaultLayouts: 
            return

        if self._tile_layout in {"top", "bottom"}:

            tab_w = "?" if self.hide_page_handles else "w*0.95"

            self.vertical_sizes = {"navigation": "h*0.05", "tab": "?", "inner": 0, "outer": 0}                
            self.horizontal_sizes = {"tab": tab_w,"navigation": "w"}

            col_size = self.navigation_tile_size
            if isinstance(col_size, float) and col_size < 1:
                col_size = f"w*{col_size}"

            nav_dict = {"columns": None, "rows": 1, 
                        "column_sizes": col_size, "row_sizes" : "?",
                        "outer_margins": [3,"?",0,"w*0.025"]}

            line_or = "horizontal"
            line_al = "top"
            hide = ()
            ##Should set all values here that are required
            horizontal_sizes = {"icon": "r", "inner": "r/3", "line": "w", "outer": 0}
            vertical_sizes = {"line": 7, "inner": 3, "outer": 0}
        elif self._tile_layout in {"left", "right"}:
            tab_h = "?" if self.hide_page_handles else "h*0.95"
            
            self.vertical_sizes = {"navigation": "h", "tab": tab_h}
            self.horizontal_sizes = {"navigation": "w*0.05","tab": "?"}

            row_size = self.navigation_tile_size
            if isinstance(row_size, float) and row_size < 1:
                row_size = f"h*{row_size}"

            nav_dict = {"columns": 1, "rows": None, "column_sizes": "?",
                        "row_sizes": row_size, "outer_margins": ["h*0.025",0,"?",0]}

            line_or = "vertical"
            line_al = "right" if self._tile_layout == "left" else "left"
            hide = ("name",)
            horizontal_sizes = {"line": 7, "inner": 3, "outer": 3, "icon": "?"}
            vertical_sizes = {"line": "h", "outer": 0, "inner": "?"}
        else:
            return

        upd_attr = {"hide": hide, "horizontal_sizes": horizontal_sizes, "vertical_sizes": vertical_sizes, 
                    "element_properties": {"line": {"orientation": line_or, "alignment": line_al}}}
        
        if not tiles:
            tiles = self.NavigationBar.elements
        for tile in tiles:
            tile : NavigationTile
            if tile._tile_layout == "auto":
                tile.update(upd_attr, skipGen=self.isGenerating, skipPrint=True)
        
        self.NavigationBar.update(nav_dict, skipGen=self.isGenerating, skipPrint=self.isUpdating, updated=True)
        self._resize_defaults = False

    def generator(self, area=None, skipNonLayoutGen=False):

        if self._resize_defaults:
            self._set_default_sizes()
            self._rebuild_area_matrix = True

        img = super().generator(area, skipNonLayoutGen)
        return img
    
    async def async_generate(self, area=None, skipNonLayoutGen=False):
        async with self._generatorLock:
            if self._resize_defaults:
                self._set_default_sizes()
                self._rebuild_area_matrix = True
        img = await super().async_generate(area, skipNonLayoutGen)
        return img

    async def async_update(self, updateAttributes={}, skipGen=False, forceGen: bool = False, skipPrint=False, reprintOnTop=False, updated: bool = False) -> bool:
        return await super().async_update(updateAttributes, skipGen, forceGen, skipPrint, reprintOnTop, updated)

