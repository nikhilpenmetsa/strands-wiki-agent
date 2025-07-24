class ChatApp {
    constructor() {
        this.apiUrl = null;
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.chatMessages = document.getElementById('chatMessages');
        this.loading = document.getElementById('loading');
        this.sessionId = null; // Track conversation session
        
        this.init();
    }
    
    async init() {
        try {
            // Load API configuration
            const response = await fetch('/config.json');
            const config = await response.json();
            this.apiUrl = config.apiUrl + 'kb';
            
            // Enable input after config is loaded
            this.messageInput.disabled = false;
            this.sendButton.disabled = false;
            
            this.setupEventListeners();
        } catch (error) {
            this.addMessage('Error loading configuration. Please refresh the page.', 'bot');
        }
    }
    
    setupEventListeners() {
        this.sendButton.addEventListener('click', () => this.sendMessage());
        
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }
    
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message) return;
        
        // Add user message
        this.addMessage(message, 'user');
        this.messageInput.value = '';
        
        // Show loading
        this.setLoading(true);
        
        // Store session ID for conversation context
        const sessionId = this.sessionId;
        
        try {
            const response = await fetch(this.apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    prompt: message,
                    sessionId: sessionId
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            // Store the session ID for future requests
            this.sessionId = data.sessionId;
            
            // Add bot message with citations
            this.addMessageWithCitations(data.response, data.citations);
            
        } catch (error) {
            console.error('Error:', error);
            this.addMessage('Sorry, I encountered an error. Please try again.', 'bot');
        } finally {
            this.setLoading(false);
        }
    }
    
    addMessage(content, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}-message`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = content;
        
        messageDiv.appendChild(contentDiv);
        this.chatMessages.appendChild(messageDiv);
        
        // Scroll to bottom
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
    
    addMessageWithCitations(content, citations) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot-message';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        // If we have citations with spans, highlight them in the text
        if (citations && citations.length > 0) {
            // Sort citations by span start position (descending) to avoid index shifting
            const sortedCitations = [...citations].sort((a, b) => {
                if (!a.span || !b.span) return 0;
                return b.span.start - a.span.start;
            });
            
            // Start with the full text
            let processedContent = content;
            
            // Replace each span with highlighted version
            sortedCitations.forEach((citation, index) => {
                if (citation.span) {
                    const { start, end } = citation.span;
                    if (start >= 0 && end > start && end <= processedContent.length) {
                        const before = processedContent.substring(0, start);
                        const highlighted = processedContent.substring(start, end);
                        const after = processedContent.substring(end);
                        
                        // Create tooltip content
                        const sourceFile = citation.source.split('/').pop();
                        const tooltipContent = `Source: ${sourceFile}<br>Excerpt: ${citation.content.substring(0, 100)}...`;
                        
                        processedContent = `${before}<span class="highlighted-text" data-citation-id="${index}">${highlighted}<span class="citation-tooltip">${tooltipContent}</span></span>${after}`;
                    }
                }
            });
            
            // Set HTML content with highlights
            contentDiv.innerHTML = processedContent;
            
            // Add citations section
            const citationsContainer = document.createElement('div');
            citationsContainer.className = 'citations-container';
            citationsContainer.innerHTML = '<strong>Sources:</strong><br>';
            
            citations.forEach((citation, index) => {
                const sourceFile = citation.source.split('/').pop();
                citationsContainer.innerHTML += `[${index + 1}] ${sourceFile}<br>`;
            });
            
            contentDiv.appendChild(citationsContainer);
        } else {
            // No citations, just set the text content
            contentDiv.textContent = content;
        }
        
        messageDiv.appendChild(contentDiv);
        this.chatMessages.appendChild(messageDiv);
        
        // Scroll to bottom
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
    
    setLoading(isLoading) {
        this.loading.style.display = isLoading ? 'flex' : 'none';
        this.messageInput.disabled = isLoading;
        this.sendButton.disabled = isLoading;
    }
}

// Initialize the chat app when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new ChatApp();
});