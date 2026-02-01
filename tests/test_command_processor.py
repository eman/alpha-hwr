
import pytest
from alpha_hwr.command_processor import CommandProcessor
from alpha_hwr.client import AlphaHWRClient
from unittest.mock import patch

class TestCommandProcessor:
    @pytest.mark.asyncio
    async def test_init_and_set_client(self):
        client = AlphaHWRClient("00:00:00:00:00:00")
        
        # Mock the parser so we don't need a real file
        from unittest.mock import patch
        with patch("alpha_hwr.command_processor.GeniProfileParser"):
             proc = CommandProcessor(client, "dummy_path.xml")
             assert proc.client == client
             assert proc.parser is not None

    @pytest.mark.asyncio
    async def test_initialize(self):
        client = AlphaHWRClient("00:00:00:00:00:00")
        with patch("alpha_hwr.command_processor.GeniProfileParser") as MockParser:
             mock_parser_instance = MockParser.return_value
             # Setup mock parameters
             mock_parser_instance.parameters = [1, 2, 3] # Dummy list
             
             proc = CommandProcessor(client, "dummy_path.xml")
             proc.initialize()
             
             mock_parser_instance.parse.assert_called_once()
             assert proc._initialized is True

    # More tests could be added here if CommandProcessor logic was complex
    # Currently it mostly delegates to client or handles simple logic
