import { test, expect } from '@playwright/test';

test.describe('RAG Q&A Flow', () => {
  // Common selectors (assuming they are the same as in the GPU purchase test)
  const chatInputSelector = 'input[placeholder*="Type your message"]'; 
  const sendButtonSelector = 'button:has-text("Send")'; 
  const askDocsButtonSelector = 'button:has-text("Ask Docs: What is Swisper?")'; 
  // More specific selectors based on SwisperChat.jsx structure:
  const messageContainerSelector = '.bg-gray-100.rounded-lg'; // The main chat area
  const userMessageTextSelector = (text) => `${messageContainerSelector} > div.text-right:has-text("${text}")`;
  const assistantMessageTextSelector = (text) => `${messageContainerSelector} > div.text-left:has-text("${text}")`;
  const lastAssistantMessageSelector = `${messageContainerSelector} > div.text-left:has-text("Swisper:") >> nth=-1`;
  const lastUserMessageSelector = `${messageContainerSelector} > div.text-right:has-text("You:") >> nth=-1`;


  // Helper function to send a message via input and wait for a new assistant response
  async function sendMessageAndWaitForResponse(page, message) {
    const initialResponseCount = await page.locator(lastAssistantMessageSelector).count(); // Count existing assistant messages
    
    await page.fill(chatInputSelector, message);
    await page.click(sendButtonSelector);
    
    // Wait for a new assistant message to appear
    // This locator finds the *new* last assistant message that wasn't there before.
    await expect(page.locator(lastAssistantMessageSelector)).toHaveCount(initialResponseCount + 1, { timeout: 15000 });
    return page.locator(lastAssistantMessageSelector);
  }
  
  // Helper function to click a button and wait for a new assistant response
  async function clickButtonAndWaitForResponse(page, buttonSelector) {
    const initialUserMessageCount = await page.locator(lastUserMessageSelector).count();
    const initialAssistantMessageCount = await page.locator(lastAssistantMessageSelector).count();
    
    await page.click(buttonSelector);
    
    // Wait for the user message (from button click) to appear
    await expect(page.locator(lastUserMessageSelector)).toHaveCount(initialUserMessageCount + 1, { timeout: 10000 });
    // Wait for the assistant's response to that message
    await expect(page.locator(lastAssistantMessageSelector)).toHaveCount(initialAssistantMessageCount + 1, { timeout: 15000 });
    
    return page.locator(lastAssistantMessageSelector);
  }

  test('should answer "What is Swisper?" using the Ask Docs button', async ({ page }) => {
    await page.goto('/');

    const assistantResponseLocator = await clickButtonAndWaitForResponse(page, askDocsButtonSelector);
    
    // Verify user message appeared correctly
    const lastUserMessageLocator = page.locator(lastUserMessageSelector);
    await expect(lastUserMessageLocator).toContainText('#rag What is Swisper?');
    
    // Verify assistant's response (content from docs/sample.txt or docs/features.txt)
    // Example: "Swisper is an AI assistant that helps with various tasks."
    // The RAG response might be longer, so check for a key phrase.
    // Based on sample.txt "Swisper is an AI assistant that helps with various tasks."
    await expect(assistantResponseLocator).toContainText('Swisper is an AI assistant', { timeout: 10000 });
  });

  test('should answer a typed RAG query about features', async ({ page }) => {
    await page.goto('/');

    const assistantResponseLocator = await sendMessageAndWaitForResponse(page, '#rag What are Swisper features?');
    
    // Verify user message appeared
    const lastUserMessageLocator = page.locator(lastUserMessageSelector);
    await expect(lastUserMessageLocator).toContainText('#rag What are Swisper features?');

    // Verify assistant's response (content from docs/features.txt)
    // Example: "Swisper helps manage contracts efficiently."
    await expect(assistantResponseLocator).toContainText('manage contracts efficiently', { timeout: 10000 });
  });
});
