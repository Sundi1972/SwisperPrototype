import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call
import os

# Adjust import based on how tests are run and PYTHONPATH.
# This assumes 'swisper' is a package and tests are run in a way that can find it.
from swisper.orchestrator.core import handle, Message
# For mocking PRODUCT_SELECTION_PIPELINE and async_client, we need to patch them where they are defined/imported.
# If PRODUCT_SELECTION_PIPELINE is initialized at module level in orchestrator.core,
# we might need to patch its creation function if direct patching is tricky.

# It's often easier to patch the functions/objects directly where they are used if they are module-level.
# For example, patch 'swisper.orchestrator.core.PRODUCT_SELECTION_PIPELINE.run'
# and 'swisper.orchestrator.core.ask_document_pipeline'
# and 'swisper.orchestrator.core.async_client'

@pytest.fixture(autouse=True) # Autouse to ensure environment variable is set for all tests
def set_openai_api_key():
    # Mock OpenAI API key for tests if components rely on it during initialization
    original_value = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "test_key_for_pytest"
    yield
    if original_value is None:
        del os.environ["OPENAI_API_KEY"]
    else:
        os.environ["OPENAI_API_KEY"] = original_value


@pytest.fixture
def mock_session_store():
    # Patch 'session_store' in the 'swisper.orchestrator.core' module's namespace
    with patch('swisper.orchestrator.core.session_store') as mock_store:
        mock_store.get_pending_confirmation.return_value = None
        mock_store.get_chat_history.return_value = []
        # Ensure other methods don't do anything unexpected if called
        mock_store.set_pending_confirmation = MagicMock()
        mock_store.clear_pending_confirmation = MagicMock()
        mock_store.add_chat_message = MagicMock()
        mock_store.save_session = MagicMock()
        yield mock_store

@pytest.fixture
def mock_product_pipeline_run():
    # Patch the .run() method of the PRODUCT_SELECTION_PIPELINE instance
    # This assumes PRODUCT_SELECTION_PIPELINE is successfully initialized in orchestrator.core
    # If its initialization can fail or is complex, patching create_product_selection_pipeline might be better.
    try:
        with patch('swisper.orchestrator.core.PRODUCT_SELECTION_PIPELINE.run') as mock_run:
            mock_run.return_value = {
                "ProductSelector": ({"selected_product": {"name": "Mock GPU X", "price": 299.99}}, "output_1")
            }
            yield mock_run
    except AttributeError: # Handle cases where PRODUCT_SELECTION_PIPELINE might be None due to init failure
        # If PRODUCT_SELECTION_PIPELINE itself is None, we can't patch its 'run' method.
        # So, we patch the 'create_product_selection_pipeline' function to return a mock pipeline.
        with patch('swisper.orchestrator.core.create_product_selection_pipeline') as mock_create_pipeline:
            mock_pipeline_instance = MagicMock()
            mock_pipeline_instance.run.return_value = {
                "ProductSelector": ({"selected_product": {"name": "Mock GPU X", "price": 299.99}}, "output_1")
            }
            mock_create_pipeline.return_value = mock_pipeline_instance
            # This requires orchestrator.core to re-fetch or use the mocked create_product_selection_pipeline
            # if PRODUCT_SELECTION_PIPELINE is initialized globally.
            # For simplicity, the primary patch target is the .run method of the instance.
            # This fallback might be needed if tests are run where the pipeline init in core.py fails.
            # Re-importing or reloading orchestrator.core might be needed for this to take effect if it's module-level.
            # This is getting complex; the primary patch on PRODUCT_SELECTION_PIPELINE.run is preferred.
            # If PRODUCT_SELECTION_PIPELINE is None, the test for contract path should gracefully handle it or be skipped.
            yield mock_pipeline_instance.run


@pytest.fixture
def mock_ask_doc():
    with patch('swisper.orchestrator.core.ask_document_pipeline') as mock_ask:
        mock_ask.return_value = "RAG answer: Swisper is a helpful AI."
        yield mock_ask

@pytest.fixture
def mock_openai_chat_completions_create():
    # Path to the create method of the async_client instance in orchestrator.core
    # We use AsyncMock for async methods.
    with patch('swisper.orchestrator.core.async_client.chat.completions.create', new_callable=AsyncMock) as mock_create:
        # Simulate the structure of the OpenAI API response
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "LLM chat reply."
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_create.return_value = mock_response
        yield mock_create

@pytest.mark.asyncio
async def test_contract_path_product_found(mock_session_store, mock_product_pipeline_run, mock_openai_chat_completions_create, mock_ask_doc):
    messages = [Message(role="user", content="I want to buy a GPU")]
    session_id = "test_contract_session"
    
    response = await handle(messages, session_id)

    mock_product_pipeline_run.assert_called_once_with(query="I want to buy a GPU")
    mock_session_store.set_pending_confirmation.assert_called_once_with(
        session_id, {"name": "Mock GPU X", "price": 299.99}
    )
    assert "I found this product: Mock GPU X (Price: 299.99)" in response["reply"]
    assert "Would you like to confirm this order?" in response["reply"]
    
    # Check chat history additions
    # First call: user message
    mock_session_store.add_chat_message.assert_any_call(session_id, {"role": "user", "content": "I want to buy a GPU"})
    # Second call: assistant's reply
    mock_session_store.add_chat_message.assert_any_call(session_id, {"role": "assistant", "content": response["reply"]})
    mock_session_store.save_session.assert_called_with(session_id) # Should be called once at the end

@pytest.mark.asyncio
async def test_confirmation_yes_path(mock_session_store, mock_product_pipeline_run, mock_openai_chat_completions_create, mock_ask_doc):
    session_id = "test_confirm_yes"
    pending_product = {"name": "Mock GPU Y", "price": 350}
    mock_session_store.get_pending_confirmation.return_value = pending_product
    
    # Simulate existing chat history for the artifact
    initial_history = [
        {"role": "user", "content": "I want to buy GPU Y"},
        {"role": "assistant", "content": "Found Mock GPU Y... confirm?"}
    ]
    mock_session_store.get_chat_history.return_value = initial_history

    messages = [Message(role="user", content="yes")]

    # Mock file operations for artifact saving
    with patch('swisper.orchestrator.core.os.makedirs') as mock_makedirs, \
         patch('builtins.open', new_callable=MagicMock) as mock_open, \
         patch('swisper.orchestrator.core.json.dump') as mock_json_dump:
        
        response = await handle(messages, session_id)

    assert "Great! Order confirmed for Mock GPU Y" in response["reply"]
    mock_makedirs.assert_called_once_with("tmp/contracts", exist_ok=True)
    # Path for artifact includes timestamp, so difficult to assert exact path with mock_open.
    # Check that open was called (implies attempt to write) and json.dump was called.
    assert mock_open.called 
    assert mock_json_dump.called
    
    # Verify the content passed to json.dump
    # args[0] of mock_json_dump.call_args is the first positional argument (the data)
    artifact_data_dumped = mock_json_dump.call_args[0][0]
    assert artifact_data_dumped["session_id"] == session_id
    assert artifact_data_dumped["confirmed_product"] == pending_product
    assert "confirmation_time" in artifact_data_dumped
    assert artifact_data_dumped["chat_history_at_confirmation"] == initial_history # Plus the "yes" message if it was added before this specific get_chat_history call

    mock_session_store.clear_pending_confirmation.assert_called_once_with(session_id)
    mock_session_store.add_chat_message.assert_any_call(session_id, {"role": "user", "content": "yes"})


@pytest.mark.asyncio
async def test_confirmation_no_path(mock_session_store, mock_product_pipeline_run, mock_openai_chat_completions_create, mock_ask_doc):
    session_id = "test_confirm_no"
    pending_product = {"name": "Mock GPU Z", "price": 400}
    mock_session_store.get_pending_confirmation.return_value = pending_product
    messages = [Message(role="user", content="no")]

    response = await handle(messages, session_id)

    assert "Okay, the order for Mock GPU Z has been cancelled." in response["reply"]
    mock_session_store.clear_pending_confirmation.assert_called_once_with(session_id)
    mock_session_store.add_chat_message.assert_any_call(session_id, {"role": "user", "content": "no"})


@pytest.mark.asyncio
async def test_rag_path(mock_session_store, mock_product_pipeline_run, mock_openai_chat_completions_create, mock_ask_doc):
    session_id = "test_rag_session"
    messages = [Message(role="user", content="#rag What is Swisper?")]
    
    response = await handle(messages, session_id)

    mock_ask_doc.assert_called_once_with(question="What is Swisper?")
    assert response["reply"] == "RAG answer: Swisper is a helpful AI."
    mock_product_pipeline_run.assert_not_called() # Ensure contract path not taken
    mock_openai_chat_completions_create.assert_not_called() # Ensure general chat path not taken
    mock_session_store.add_chat_message.assert_any_call(session_id, {"role": "user", "content": "#rag What is Swisper?"})


@pytest.mark.asyncio
async def test_chat_path(mock_session_store, mock_product_pipeline_run, mock_openai_chat_completions_create, mock_ask_doc):
    session_id = "test_chat_session"
    user_message = "Hello, how are you?"
    messages = [Message(role="user", content=user_message)]
    
    # Simulate some history for the LLM call
    chat_history_for_llm = [{"role": "user", "content": user_message}]
    mock_session_store.get_chat_history.return_value = chat_history_for_llm

    response = await handle(messages, session_id)

    mock_openai_chat_completions_create.assert_called_once_with(model="gpt-4o", messages=chat_history_for_llm)
    assert response["reply"] == "LLM chat reply."
    mock_product_pipeline_run.assert_not_called()
    mock_ask_doc.assert_not_called()
    mock_session_store.add_chat_message.assert_any_call(session_id, {"role": "user", "content": user_message})

# Add more tests:
# - Test for when RAG_AVAILABLE is False (ask_doc should use dummy, or orchestrator handles it)
# - Test for when PRODUCT_SELECTION_PIPELINE is None (contract path is skipped)
# - Test for when product pipeline finds no product
# - Test for empty message to #rag trigger
# - Test for ambiguous confirmation response
# - Test for errors during pipeline execution or LLM calls (though some are implicitly covered if mocks raise errors)
# - Test for session_id in artifact path sanitization (if you want to be very thorough)
# - Test for when OPENAI_API_KEY is not set and async_client is None (chat path should return error)
# - Test for empty messages list to handle()
# - Test for add_chat_message calls count and order for more complex interactions
# - Test for save_session calls count (should be once per handle call at the end)
# - Test the try-except block for importing contract_engine.contract_pipeline (might be hard to unit test directly)
# - Test the try-except block for importing haystack_pipeline (RAG_AVAILABLE flag)
# - Test the try-except blocks for OpenAI client and Product Selection Pipeline initialization (how handle behaves if they are None)

@pytest.mark.asyncio
async def test_rag_path_rag_unavailable(mock_session_store, mock_product_pipeline_run, mock_openai_chat_completions_create):
    # Temporarily patch RAG_AVAILABLE and ask_document_pipeline in orchestrator.core
    with patch('swisper.orchestrator.core.RAG_AVAILABLE', False), \
         patch('swisper.orchestrator.core.ask_document_pipeline') as mock_dummy_ask_doc:
        # The dummy ask_doc defined in core.py will be used if RAG_AVAILABLE is False at import time.
        # If we patch RAG_AVAILABLE after import, we also need to ensure the dummy function is what's called.
        # The dummy function is: `def ask_document_pipeline(question: str): return "RAG system is currently unavailable due to an import error."`
        # So, we don't need to mock its return value here if we are testing that the orchestrator uses the dummy.
        # However, for clarity or if the dummy changes, explicitly mocking its behavior in the test is safer.
        mock_dummy_ask_doc.return_value = "RAG system is currently unavailable due to an import error."

        session_id = "test_rag_unavailable"
        messages = [Message(role="user", content="#rag Test question")]
        response = await handle(messages, session_id)
        
        # Check that the dummy/fallback response is given
        assert response["reply"] == "RAG system is currently unavailable due to an import error."
        mock_dummy_ask_doc.assert_called_once_with(question="Test question") # Ensure our patched ask_doc was called.

@pytest.mark.asyncio
async def test_contract_path_pipeline_unavailable(mock_session_store, mock_openai_chat_completions_create, mock_ask_doc):
    # Patch PRODUCT_SELECTION_PIPELINE to be None in orchestrator.core
    with patch('swisper.orchestrator.core.PRODUCT_SELECTION_PIPELINE', None):
        session_id = "test_pipeline_unavailable"
        user_message = "I want to buy a GPU"
        messages = [Message(role="user", content=user_message)]
        
        chat_history_for_llm = [{"role": "user", "content": user_message}]
        mock_session_store.get_chat_history.return_value = chat_history_for_llm

        response = await handle(messages, session_id)
        
        # Should fall back to chat path
        mock_openai_chat_completions_create.assert_called_once_with(model="gpt-4o", messages=chat_history_for_llm)
        assert response["reply"] == "LLM chat reply."
        mock_ask_doc.assert_not_called()

@pytest.mark.asyncio
async def test_contract_path_no_product_found(mock_session_store, mock_product_pipeline_run, mock_openai_chat_completions_create, mock_ask_doc):
    session_id = "test_no_product_found"
    user_message = "Buy a very specific obscure item"
    messages = [Message(role="user", content=user_message)]
    
    # Configure mock_product_pipeline_run to return no selected product
    mock_product_pipeline_run.return_value = {"ProductSelector": ({"selected_product": None}, "output_1")}

    response = await handle(messages, session_id)

    mock_product_pipeline_run.assert_called_once_with(query=user_message)
    assert "Sorry, I couldn't find a suitable product" in response["reply"]
    mock_session_store.set_pending_confirmation.assert_not_called()
    mock_openai_chat_completions_create.assert_not_called()

@pytest.mark.asyncio
async def test_rag_path_empty_question(mock_session_store, mock_product_pipeline_run, mock_ask_doc, mock_openai_chat_completions_create):
    session_id = "test_rag_empty_q"
    messages = [Message(role="user", content="#rag ")] # Note the space
    
    response = await handle(messages, session_id)
    
    assert response["reply"] == "Please provide a question after the #rag trigger."
    mock_ask_doc.assert_not_called()
    mock_product_pipeline_run.assert_not_called()
    mock_openai_chat_completions_create.assert_not_called()

@pytest.mark.asyncio
async def test_confirmation_ambiguous_response(mock_session_store, mock_product_pipeline_run, mock_openai_chat_completions_create, mock_ask_doc):
    session_id = "test_confirm_ambiguous"
    pending_product = {"name": "Mock GPU ABC", "price": 123}
    mock_session_store.get_pending_confirmation.return_value = pending_product
    messages = [Message(role="user", content="maybe later")]

    response = await handle(messages, session_id)

    assert "Sorry, I didn't quite understand. For Mock GPU ABC, please confirm with 'yes' or 'no'." in response["reply"]
    mock_session_store.clear_pending_confirmation.assert_not_called() # Should not clear yet
    mock_session_store.add_chat_message.assert_any_call(session_id, {"role": "user", "content": "maybe later"})

@pytest.mark.asyncio
async def test_empty_messages_list_to_handle(mock_session_store):
    session_id = "test_empty_messages"
    response = await handle(messages=[], session_id=session_id)
    assert "No messages provided to orchestrator" in response["reply"]
    mock_session_store.add_chat_message.assert_not_called() # Should not add if no messages
    mock_session_store.save_session.assert_not_called() # Should not save if early exit
