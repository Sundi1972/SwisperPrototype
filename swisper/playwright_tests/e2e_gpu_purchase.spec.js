import { test, expect } from '@playwright/test';

test.describe('GPU Purchase Flow', () => {
  test('should allow user to search for a GPU, get a suggestion, and confirm purchase', async ({ page }) => {
    await page.goto('/'); // Assumes baseURL 'http://localhost:5173' is set in playwright.config.js

    // Common selectors (these might need adjustment based on the actual frontend HTML structure)
    const chatInputSelector = 'input[placeholder*="Type your message"]'; 
    const sendButtonSelector = 'button:has-text("Send")'; 
    // Assuming each message is a div, and assistant messages might have a specific class or structure
    // For SwisperChat.jsx, each message is: <div key={i} className={`text-sm mb-2 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
    // So, assistant messages are divs with 'text-left' and contain "Swisper:"
    // A more robust selector might be needed if other 'text-left' divs exist.
    // Let's target the message container and then filter for assistant messages.
    const messageContainerSelector = '.bg-gray-100.rounded-lg'; // The main chat area
    
    // Helper to get the last assistant message text
    async function getLastAssistantMessageText() {
      const allMessages = await page.locator(`${messageContainerSelector} > div`).allTextContents();
      const assistantMessages = allMessages.filter(text => text.startsWith("Swisper:"));
      return assistantMessages.pop() || ""; // Return last or empty string
    }

    // Helper function to send a message and wait for a new assistant response
    async function sendMessageAndWaitForResponse(message) {
      const initialAssistantMessages = await page.locator(`${messageContainerSelector} > div:has-text("Swisper:")`).count();
      
      await page.fill(chatInputSelector, message);
      await page.click(sendButtonSelector);
      
      // Wait for the number of assistant messages to increase
      await expect(page.locator(`${messageContainerSelector} > div:has-text("Swisper:")`)).toHaveCount(initialAssistantMessages + 1, { timeout: 20000 }); // Increased timeout for potentially slow backend
      
      return getLastAssistantMessageText();
    }

    // 1. Initiate purchase
    // The mock data includes "Mock GPU A (Super Edition)" and "Mock GPU B (Basic)".
    // Querying "Mock GPU" should ideally find "Mock GPU A (Super Edition)" if ranked by rating then price.
    const assistantResponseProductSuggestionText = await sendMessageAndWaitForResponse('I want to buy a Mock GPU');
    
    // Verify product suggestion and confirmation question
    // The product name depends on mock_gpus.json and ranking.
    // "Mock GPU A (Super Edition)" (rating 4.5, price 399.99)
    // "Mock GPU C (Pro Gamer)" (rating 4.8, price 599.00) - This should be selected by ranking logic
    expect(assistantResponseProductSuggestionText).toContain('I found this product: Mock GPU C (Pro Gamer)');
    expect(assistantResponseProductSuggestionText).toContain('Price: 599'); // Check for price, partial match is okay
    expect(assistantResponseProductSuggestionText).toContain('Would you like to confirm this order? (yes/no)');

    // 2. User confirms "yes"
    const assistantResponseConfirmationText = await sendMessageAndWaitForResponse('yes');

    // Verify order confirmation message
    expect(assistantResponseConfirmationText).toContain('Great! Order confirmed for Mock GPU C (Pro Gamer).');
    
    // Note: Verification of artifact creation in `tmp/contracts` is outside the scope of
    // a typical Playwright UI test and would require additional setup (e.g., a separate API endpoint
    // or file system access in the test environment).
  });
});
