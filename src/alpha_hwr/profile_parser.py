"""
GENI Profile Parser Module

Provides classes to parse GENI profile XML files and extract parameter definitions.
"""

import defusedxml.ElementTree as ET
from xml.etree.ElementTree import Element
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union


@dataclass
class ParameterEnum:
    """Enumeration value for a parameter"""

    name: str
    value: int
    description: Optional[str] = None


@dataclass
class Parameter:
    """GENI parameter definition"""

    name: str
    geni_class: int
    geni_id: int
    rw_type: str  # ReadOnly, ReadWrite, WriteOnly
    description: str
    data_type: Optional[str] = None  # Integer, Float, String, Enum, etc.
    unit: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    default_value: Optional[Any] = None
    enum_values: List[ParameterEnum] = field(default_factory=list)

    @property
    def register_address(self) -> int:
        """Calculate register address from class and ID"""
        return (self.geni_class << 8) | self.geni_id

    @property
    def register_hex(self) -> str:
        """Get register address as hex string"""
        return f"0x{self.register_address:04X}"


class GeniProfileParser:
    """Parser for GENI profile XML files"""

    def __init__(self, xml_path: Union[str, Path]):
        self.xml_path = Path(xml_path)
        self.parameters: List[Parameter] = []
        self.params_by_name: Dict[str, Parameter] = {}
        self.params_by_register: Dict[int, Parameter] = {}
        self._parsed = False

    def parse(self) -> None:
        """Parse the XML file and extract all parameters"""
        if self._parsed:
            return

        if not self.xml_path.exists():
            raise FileNotFoundError(f"Profile file not found: {self.xml_path}")

        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()

            # Find all parameter elements
            # Find all parameter elements
            parameters_elem = root.find(".//parameters")
            if parameters_elem is None:
                parameters_elem = root.find(".//{*}parameters")

            if parameters_elem is None:
                parameters_elem = root

            param_nodes = parameters_elem.findall(".//parameter")
            if not param_nodes:  # Empty list check is fine, it's Element truthiness that is deprecated
                param_nodes = parameters_elem.findall(".//{*}parameter")

            for param_elem in param_nodes:
                param = self._parse_parameter(param_elem)
                if param:
                    self.parameters.append(param)
                    self.params_by_name[param.name] = param
                    self.params_by_register[param.register_address] = param

            self._parsed = True

        except ET.ParseError as e:
            raise ValueError(f"Invalid XML file: {e}")

    def _parse_parameter(self, param_elem: Element) -> Optional[Parameter]:
        """Parse a single parameter element"""
        try:
            name = self._get_text(param_elem, "name")
            if not name:
                return None

            geni_class = int(self._get_text(param_elem, "class", "0"))
            geni_id = int(self._get_text(param_elem, "id", "0"))
            rw_type = self._get_text(param_elem, "rw_type", "ReadOnly")
            description = self._get_text(param_elem, "description", "")

            # Parse data type and constraints
            data_type = self._get_text(param_elem, "data_type")
            unit = self._get_text(param_elem, "unit")

            min_value = None
            max_value = None

            min_text = self._get_text(param_elem, "min")
            if min_text:
                try:
                    min_value = float(min_text)
                except ValueError:
                    pass

            max_text = self._get_text(param_elem, "max")
            if max_text:
                try:
                    max_value = float(max_text)
                except ValueError:
                    pass

            default_text = self._get_text(param_elem, "default")
            default_value: Optional[Union[int, float, str]] = None
            if default_text:
                try:
                    if "." in default_text:
                        default_value = float(default_text)
                    else:
                        default_value = int(default_text)
                except ValueError:
                    default_value = default_text

            # Parse enum values if present
            enum_values = []
            values_elem = param_elem.find("values")
            if values_elem is not None:
                for item_elem in values_elem.findall("item"):
                    enum_name = self._get_text(item_elem, "name", "")
                    enum_value_text = self._get_text(item_elem, "value", "0")
                    enum_desc = self._get_text(item_elem, "description")

                    try:
                        enum_value = int(enum_value_text)
                    except ValueError:
                        try:
                            enum_value = int(enum_value_text, 16)
                        except ValueError:
                            enum_value = 0

                    enum_values.append(
                        ParameterEnum(
                            name=enum_name,
                            value=enum_value,
                            description=enum_desc,
                        )
                    )

            # Infer data type if not specified
            if not data_type:
                if enum_values:
                    data_type = "Enum"
                elif min_value is not None or max_value is not None:
                    data_type = (
                        "Float"
                        if (min_value and "." in str(min_value))
                        else "Integer"
                    )
                else:
                    data_type = "Unknown"

            return Parameter(
                name=name,
                geni_class=geni_class,
                geni_id=geni_id,
                rw_type=rw_type,
                description=description,
                data_type=data_type,
                unit=unit,
                min_value=min_value,
                max_value=max_value,
                default_value=default_value,
                enum_values=enum_values,
            )

        except Exception:
            # Silently skip malformed parameters or log if logger available
            return None

    def _get_text(self, elem: Element, tag: str, default: str = "") -> str:
        """Get text content of a child element"""
        child = elem.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return default

    def get_by_name(self, name: str) -> Optional[Parameter]:
        """Get parameter by name"""
        if not self._parsed:
            self.parse()
        return self.params_by_name.get(name)

    def get_by_register(self, register: int) -> Optional[Parameter]:
        """Get parameter by register address"""
        if not self._parsed:
            self.parse()
        return self.params_by_register.get(register)

    def search(self, query: str) -> List[Parameter]:
        """Search parameters by name (case-insensitive substring match)"""
        if not self._parsed:
            self.parse()
        query_lower = query.lower()
        return [p for p in self.parameters if query_lower in p.name.lower()]

    def get_by_class(self, geni_class: int) -> List[Parameter]:
        """Get all parameters of a specific class"""
        if not self._parsed:
            self.parse()
        return [p for p in self.parameters if p.geni_class == geni_class]
