import pytest
from alpha_hwr.profile_parser import GeniProfileParser

# Sample XML Content
SAMPLE_XML = """
<profile>
    <parameters>
        <parameter>
            <name>SetHead</name>
            <id>1</id>
            <class>3</class>
            <rw_type>WriteOnly</rw_type>
            <description>Set Head</description>
            <data_type>Float</data_type>
            <unit>m</unit>
            <min>0.0</min>
            <max>10.0</max>
            <default>5.0</default>
        </parameter>
        <parameter>
            <name>Mode</name>
            <id>2</id>
            <class>3</class>
            <rw_type>ReadWrite</rw_type>
            <description>Control Mode</description>
            <values>
                <item>
                   <name>Auto</name>
                   <value>0</value>
                </item>
                <item>
                   <name>Manual</name>
                   <value>1</value>
                </item>
            </values>
        </parameter>
    </parameters>
</profile>
"""


class TestProfileParser:
    def test_parse_valid_xml(self, tmp_path):
        """Test parsing a valid XML file."""
        xml_file = tmp_path / "test_profile.xml"
        xml_file.write_text(SAMPLE_XML)

        parser = GeniProfileParser(xml_file)
        parser.parse()

        assert len(parser.parameters) == 2

        # Check Param 1 (SetHead)
        p1 = parser.get_by_name("SetHead")
        assert p1 is not None
        assert p1.geni_id == 1
        assert p1.geni_class == 3
        assert p1.data_type == "Float"
        assert p1.min_value == 0.0
        assert p1.max_value == 10.0
        assert p1.default_value == 5.0

        # Check Param 2 (Mode - Enum)
        p2 = parser.get_by_name("Mode")
        assert p2 is not None
        assert len(p2.enum_values) == 2
        assert p2.enum_values[0].name == "Auto"
        assert p2.enum_values[0].value == 0

    def test_search_and_getters(self, tmp_path):
        xml_file = tmp_path / "test_profile.xml"
        xml_file.write_text(SAMPLE_XML)

        parser = GeniProfileParser(xml_file)
        # Auto-parse on search
        results = parser.search("head")
        assert len(results) == 1
        assert results[0].name == "SetHead"

        # Get by register (Class 3 << 8 | ID 1 = 0x0301)
        p = parser.get_by_register(0x0301)
        assert p is not None
        assert p.name == "SetHead"

    def test_malformed_file(self, tmp_path):
        xml_file = tmp_path / "bad.xml"
        xml_file.write_text("<root><unclosed>")

        parser = GeniProfileParser(xml_file)
        with pytest.raises(ValueError, match="Invalid XML"):
            parser.parse()
