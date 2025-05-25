// DOM Elements
const chatMessages = document.getElementById('chatMessages');
const userInput = document.getElementById('userInput');
const sendButton = document.querySelector('button[onclick="sendMessage()"]');
const sitesList = document.getElementById('sitesList');
const siteUrlInput = document.getElementById('siteUrl');
const siteLoading = document.getElementById('siteLoading');
const typingIndicator = document.getElementById('typingIndicator');
const sourcesPanel = document.getElementById('sourcesPanel');
const sourcesList = document.getElementById('sourcesList');
const toast = document.getElementById('toast');
const toastMessage = document.getElementById('toastMessage');
const confirmationModal = document.getElementById('confirmationModal');
const modalTitle = document.getElementById('modalTitle');
const modalMessage = document.getElementById('modalMessage');
const confirmActionBtn = document.getElementById('confirmActionBtn');

// WebSocket
let socket;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
const reconnectDelay = 1000; // 1 second
let isScrolledToBottom = true;
let scrollToBottomBtn;
let isTyping = false;

// Initialize chat UI elements
function initChatUI() {
    // Create scroll-to-bottom button
    scrollToBottomBtn = document.createElement('button');
    scrollToBottomBtn.className = 'scroll-to-bottom hidden';
    scrollToBottomBtn.innerHTML = '↓';
    scrollToBottomBtn.title = 'Scroll to bottom';
    scrollToBottomBtn.onclick = scrollToBottom;
    document.body.appendChild(scrollToBottomBtn);

    // Add scroll event listener to chat messages container
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.addEventListener('scroll', handleChatScroll);
}

// Scroll to the bottom of the chat
function scrollToBottom(behavior = 'smooth') {
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) {
        chatMessages.scrollTo({
            top: chatMessages.scrollHeight,
            behavior: behavior
        });
        isScrolledToBottom = true;
        hideScrollToBottomButton();
    }
}

// Handle chat scroll events
function handleChatScroll() {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    // Check if user is at the bottom of the chat
    const isAtBottom = chatMessages.scrollHeight - chatMessages.scrollTop <= chatMessages.clientHeight + 100; // 100px threshold
    
    if (isAtBottom !== isScrolledToBottom) {
        isScrolledToBottom = isAtBottom;
        
        if (isScrolledToBottom) {
            hideScrollToBottomButton();
        } else {
            showScrollToBottomButton();
        }
    }
}

// Show scroll-to-bottom button
function showScrollToBottomButton() {
    if (scrollToBottomBtn) {
        scrollToBottomBtn.classList.remove('hidden');
    }
}

// Hide scroll-to-bottom button
function hideScrollToBottomButton() {
    if (scrollToBottomBtn) {
        scrollToBottomBtn.classList.add('hidden');
    }
}

// Connect to WebSocket
function connectWebSocket() {
    try {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const wsUrl = wsProtocol + window.location.host + '/ws';
        
        // Close existing connection if any
        if (socket) {
            try {
                socket.close();
            } catch (e) {
                console.log('Error closing existing WebSocket:', e);
            }
        }
        
        console.log('Connecting to WebSocket:', wsUrl);
        socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            console.log('WebSocket connected');
            reconnectAttempts = 0; // Reset reconnect attempts on successful connection
            showToast('Connected to server');
            
            // Re-enable input if it was disabled
            userInput.disabled = false;
            if (sendButton) sendButton.disabled = false;
            
            // Hide any previous error messages
            hideTypingIndicator();
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (e) {
                console.error('Error parsing WebSocket message:', e);
            }
        };

        socket.onclose = (event) => {
            console.log('WebSocket disconnected:', event.code, event.reason);
            
            // If this was an unexpected closure, try to reconnect
            if (event.code !== 1000) { // 1000 is a normal closure
                if (reconnectAttempts < maxReconnectAttempts) {
                    reconnectAttempts++;
                    const delay = Math.min(reconnectDelay * Math.pow(2, reconnectAttempts), 30000); // Cap at 30s
                    console.log(`Attempting to reconnect in ${delay/1000} seconds... (attempt ${reconnectAttempts}/${maxReconnectAttempts})`);
                    showToast(`Connection lost. Reconnecting in ${Math.ceil(delay/1000)} seconds...`, 'warning');
                    setTimeout(connectWebSocket, delay);
                } else {
                    console.error('Max reconnection attempts reached');
                    showToast('Connection failed. Please refresh the page.', 'error');
                    // Disable input to prevent further attempts
                    userInput.disabled = true;
                    if (sendButton) sendButton.disabled = true;
                }
            }
        };

        socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            // The onclose handler will be called after an error, so we'll handle reconnection there
        };
        
    } catch (error) {
        console.error('Error setting up WebSocket:', error);
        showToast('Failed to connect. Please refresh the page.', 'error');
    }
}

// Handle incoming WebSocket messages
function handleWebSocketMessage(data) {
    console.log('Received message:', data);
    
    try {
        if (data.type === 'chat_response') {
            // Check if this is a new response or an update to an existing one
            const existingMessage = document.getElementById(`message-${data.message_id}`);
            
            if (existingMessage) {
                // Update existing message
                const contentElement = existingMessage.querySelector('.message-content');
                if (contentElement) {
                    // Append chunk if it's not complete, otherwise replace
                    if (!data.is_complete && data.response) {
                        contentElement.innerHTML += marked.parse(data.response); // Append chunk
                    } else if (data.is_complete && data.response) {
                        contentElement.innerHTML = marked.parse(data.response); // Replace with full response
                    }
                    highlightCodeBlocks(contentElement);
                    
                    if (isScrolledToBottom) {
                        scrollToBottom();
                    } else {
                        showScrollToBottomButton();
                    }
                }
            } else {
                // Create new message for the initial chunk
                appendMessage('assistant', data.response, data.message_id);
                if (isScrolledToBottom) {
                    scrollToBottom();
                } else {
                    showScrollToBottomButton();
                }
            }

            if (data.is_complete) {
                // hideTypingIndicator(); // Now handled by typing:false
                userInput.disabled = false; // Re-enable input
                if (sendButton) sendButton.disabled = false; // Re-enable send button
                userInput.focus(); // Focus input for next message
            }
        } else if (data.type === 'typing') {
            if (data.is_typing) {
                isTyping = true;
                showTypingIndicator();
                userInput.disabled = true;
                if (sendButton) sendButton.disabled = true;
            } else {
                isTyping = false;
                hideTypingIndicator();
                userInput.disabled = false;
                if (sendButton) sendButton.disabled = false;
                userInput.focus();
            }
        } else if (data.type === 'sources') {
            updateSources(data.sources);
        } else if (data.type === 'error') {
            hideTypingIndicator();
            showToast(data.message || 'An error occurred', 'error');
            userInput.disabled = false; // Re-enable input on error
            if (sendButton) sendButton.disabled = false; // Re-enable send button on error
        } else if (data.type === 'site_added') {
            showToast(`Site "${data.site.name}" added. Starting crawl...`, 'info');
            loadSites(); // Re-fetch to show the new site immediately
        } else if (data.type === 'crawl_progress') {
            // Re-load sites to update progress dynamically
            loadSites();
        } else if (data.type === 'crawl_completed') {
            showToast(`Site "${data.site_id}" processing completed! ${data.total_chunks} chunks added.`, 'success');
            loadSites(); // Re-fetch to show final status and chunk count
        } else if (data.type === 'crawl_error') {
            showToast(`Error processing site "${data.site_id}": ${data.error}`, 'error');
            loadSites(); // Re-fetch to show error status
        } else if (data.type === 'site_deleted') {
            showToast(`Site "${data.site_id}" deleted.`, 'info');
            loadSites(); // Re-fetch to remove the site from the list
        } else if (data.type === 'database_cleared') {
            showToast('All documentation cleared from the database.', 'info');
            loadSites(); // This will clear the sites list in UI
            chatMessages.innerHTML = `
                <div class="text-center text-gray-500 mt-10">
                    <i class="fas fa-comment-alt text-4xl mb-2"></i>
                    <p>Ask me anything about the documentation</p>
                </div>
            `;
            sourcesList.innerHTML = ''; // Clear sources panel content
            sourcesPanel.classList.add('hidden'); // Hide sources panel
        }
    } catch (error) {
        console.error('Error handling WebSocket message:', error);
        showToast('Error processing message', 'error');
        userInput.disabled = false; // Ensure input is re-enabled on any WebSocket error
        if (sendButton) sendButton.disabled = false;
    }
}

// Append a message to the chat
function appendMessage(role, content, messageId = null) {
    try {
        const chatMessages = document.getElementById('chatMessages');
        if (!chatMessages) return null;
        
        // Generate a unique ID for the message if not provided
        const msgId = messageId || `msg-${Date.now()}`;
        
        // Create message container
        const messageDiv = document.createElement('div');
        messageDiv.id = `message-${msgId}`;
        messageDiv.className = `message ${role} new-message`;
        
        // Format the content with markdown
        const formattedContent = marked.parse(content || '');
        
        // Create message content with loading state
        messageDiv.innerHTML = `
            <div class="message-content">${formattedContent}</div>
        `;
        
        // Add to the chat
        chatMessages.appendChild(messageDiv);
        
        // Highlight code blocks
        highlightCodeBlocks(messageDiv);
        
        // Trigger reflow to ensure animation plays
        void messageDiv.offsetWidth;
        messageDiv.classList.add('fade-in');
        
        // Only auto-scroll if user is at the bottom
        if (isScrolledToBottom) {
            scrollToBottom();
        } else {
            showScrollToBottomButton();
        }
        
        return messageDiv;
    } catch (error) {
        console.error('Error appending message:', error);
        return null;
    }
}

// Highlight code blocks with Prism.js
function highlightCodeBlocks(container) {
    if (typeof Prism !== 'undefined' && container) {
        const codeBlocks = container.querySelectorAll('pre code');
        codeBlocks.forEach(block => {
            // Only highlight if not already highlighted
            if (!block.classList.contains('language-')) {
                // Attempt to infer language from class or default to 'none'
                let lang = 'none';
                const classList = Array.from(block.classList);
                for (const cls of classList) {
                    if (cls.startsWith('language-')) {
                        lang = cls.substring(9);
                        break;
                    }
                }
                // Simple heuristics for common languages if not specified
                if (lang === 'none') {
                    if (block.textContent.includes('import') && block.textContent.includes('def')) {
                        lang = 'python';
                    } else if (block.textContent.includes('function') || block.textContent.includes('const') || block.textContent.includes('let')) {
                        lang = 'javascript';
                    } else if (block.textContent.includes('<') && block.textContent.includes('>')) {
                        lang = 'markup'; // For HTML/XML
                    } else if (block.textContent.includes('{') && block.textContent.includes(';')) {
                        lang = 'css';
                    }
                }
                block.classList.add(`language-${lang}`);
                Prism.highlightElement(block);
            }
        });
    }
}


// Show typing indicator
function showTypingIndicator() {
    const typingIndicator = document.getElementById('typingIndicator');
    if (typingIndicator) {
        typingIndicator.classList.remove('hidden');
        
        // Ensure the indicator is visible in the viewport
        typingIndicator.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        
        // Auto-hide after 10 seconds if no response is received
        clearTimeout(window.typingTimeout);
        window.typingTimeout = setTimeout(() => {
            hideTypingIndicator();
        }, 10000);
    }
}

// Hide typing indicator
function hideTypingIndicator() {
    isTyping = false;
    clearTimeout(window.typingTimeout);
    const typingIndicator = document.getElementById('typingIndicator');
    if (typingIndicator) {
        typingIndicator.classList.add('hidden');
    }
}

// Show toast notification
function showToast(message, level = 'info') {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toastMessage');
    
    if (!toast || !toastMessage) return;
    
    toastMessage.textContent = message;
    
    // Reset toast classes
    toast.className = 'fixed bottom-4 right-4 px-4 py-2 rounded-lg shadow-lg transform translate-y-10 opacity-0 transition-all duration-300';
    
    // Set background color based on level
    switch (level) {
        case 'success':
            toast.classList.add('bg-green-600', 'text-white');
            break;
        case 'error':
            toast.classList.add('bg-red-600', 'text-white');
            break;
        case 'warning':
            toast.classList.add('bg-yellow-500', 'text-white');
            break;
        default:
            toast.classList.add('bg-gray-800', 'text-white');
    }
    
    // Show toast
    toast.classList.remove('translate-y-10', 'opacity-0');
    toast.classList.add('translate-y-0', 'opacity-100');
    
    // Hide after delay
    setTimeout(() => {
        toast.classList.remove('translate-y-0', 'opacity-100');
        toast.classList.add('translate-y-10', 'opacity-0');
    }, 5000);
}

// Add a new site for crawling
async function addSite() {
    const url = siteUrlInput.value.trim();
    if (!url) {
        showToast('Please enter a URL to add.', 'warning');
        return;
    }

    siteLoading.classList.remove('hidden');
    
    try {
        const response = await fetch('/api/add-site', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, name: url })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to add site');
        }
        
        const data = await response.json();
        // showToast(`Added ${data.name || 'site'} for processing`); // Toast handled by WebSocket now
        siteUrlInput.value = '';
        // loadSites(); // Handled by WebSocket now
    } catch (error) {
        console.error('Error adding site:', error);
        showToast(error.message, 'error');
    } finally {
        siteLoading.classList.add('hidden');
    }
}

// Load all sites
async function loadSites() {
    try {
        const response = await fetch('/api/sites');
        if (!response.ok) throw new Error('Failed to load sites');
        
        const { sites } = await response.json();
        renderSitesList(sites);
        // Fetch crawl status for each site and update
        for (const site of sites) {
            updateCrawlStatus(site.id);
        }
    } catch (error) {
        console.error('Error loading sites:', error);
        showToast('Failed to load sites', 'error');
    }
}

// Periodically update crawl status for active sites
setInterval(() => {
    const siteItems = document.querySelectorAll('.site-item');
    siteItems.forEach(item => {
        const siteId = item.getAttribute('data-id');
        const statusElem = item.querySelector('.text-xs.text-gray-400');
        if (statusElem && (statusElem.textContent.includes('crawling') || statusElem.textContent.includes('finding_urls') || statusElem.textContent.includes('starting'))) {
            updateCrawlStatus(siteId);
        }
    });
}, 2000);

// Fetch crawl status for a site and update its UI
async function updateCrawlStatus(siteId) {
    try {
        const response = await fetch(`/api/crawl-status/${siteId}`);
        if (!response.ok) return;
        const status = await response.json();
        // Find the site-item in the DOM
        const siteElem = document.querySelector(`.site-item[data-id="${siteId}"]`);
        if (!siteElem) return;
        // Update progress bar and status fields
        const progressBar = siteElem.querySelector('.progress-bar-container .bg-blue-400');
        if (progressBar && status.progress !== undefined) {
            progressBar.style.width = `${status.progress.toFixed(1)}%`;
        }
        // Update status text
        const statusElem = siteElem.querySelector('.text-xs.text-gray-400');
        if (statusElem) {
            let statusText = '';
            if (status.status === 'crawling' || status.status === 'finding_urls' || status.status === 'starting') {
                statusText = `Progress: ${status.progress !== undefined ? status.progress.toFixed(1) + '%' : '0.0%'} `;
                if (status.current_url) statusText += `Current: ${status.current_url.substring(0, 40)}...`;
            } else {
                statusText = formatStatus(status.status);
            }
            statusElem.textContent = statusText;
        }
        // Update chunks added
        let chunksElem = siteElem.querySelector('.chunks-added');
        if (!chunksElem && status.chunks_added !== undefined) {
            // Insert after progress bar
            const progressBarContainer = siteElem.querySelector('.progress-bar-container');
            if (progressBarContainer) {
                chunksElem = document.createElement('p');
                chunksElem.className = 'text-xs text-gray-400 mt-1 chunks-added';
                progressBarContainer.insertAdjacentElement('afterend', chunksElem);
            }
        }
        if (chunksElem && status.chunks_added !== undefined) {
            chunksElem.textContent = `Chunks Added: ${status.chunks_added}`;
        }
        // Update error message
        let errorElem = siteElem.querySelector('.crawl-error');
        if (!errorElem && status.error) {
            errorElem = document.createElement('p');
            errorElem.className = 'text-xs text-red-400 mt-1 crawl-error';
            siteElem.appendChild(errorElem);
        }
        if (errorElem) {
            errorElem.textContent = status.error ? `Error: ${status.error}` : '';
        }
    } catch (error) {
        // Ignore errors for missing status
    }
}


// Render sites list
function renderSitesList(sites) {
    if (!sites || sites.length === 0) {
        sitesList.innerHTML = '<p class="text-sm text-gray-400">No sites added yet</p>';
        return;
    }

    sitesList.innerHTML = sites.map(site => `
        <div class="site-item ${getStatusBgClass(site.status)}" data-id="${site.id}">
            <div class="flex justify-between items-start">
                <div class="flex-1 min-w-0">
                    <p class="font-medium truncate text-white">${site.name || 'Untitled'}</p>
                    <p class="text-xs text-gray-400 truncate">${site.url}</p>
                </div>
                <div class="flex items-center space-x-2">
                    <span class="status-indicator ${getStatusClass(site.status)}"></span>
                    <span class="text-xs text-gray-400">
                        ${(site.status === 'crawling' || site.status === 'finding_urls' || site.status === 'starting') ? 
                            `Progress: ${site.progress !== undefined ? site.progress.toFixed(1) + '%' : '0.0%'}` : 
                            formatStatus(site.status)}
                    </span>
                    <button onclick="deleteSite('${site.id}', event)" class="text-gray-400 hover:text-red-400">
                        <i class="fas fa-trash-alt text-xs"></i>
                    </button>
                </div>
            </div>
            ${(site.status === 'crawling' || site.status === 'finding_urls' || site.status === 'starting') ? `
                <div class="mt-2 w-full bg-gray-600 rounded-full h-1.5 progress-bar-container">
                    <div class="bg-blue-400 h-1.5 rounded-full" style="width: ${site.progress || 0}%"></div>
                </div>
                ${site.current_url ? `<p class="text-xs text-gray-400 mt-1 truncate">Current: ${site.current_url}</p>` : ''}
                ${site.chunks_added !== undefined ? `<p class="text-xs text-gray-400 mt-1">Chunks Added: ${site.chunks_added}</p>` : ''}
            ` : ''}
            ${site.status === 'completed' ? `<p class="text-xs text-gray-400 mt-1">Total Chunks: ${site.total_chunks || 0}</p>` : ''}
            ${site.status === 'error' && site.error ? `<p class="text-xs text-red-400 mt-1">Error: ${site.error}</p>` : ''}
        </div>
    `).join('');
}

// Get status class for styling
function getStatusClass(status) {
    const statusClasses = {
        'starting': 'status-starting',
        'finding_urls': 'status-finding_urls',
        'crawling': 'status-crawling',
        'completed': 'status-completed',
        'error': 'status-error'
    };
    return statusClasses[status] || '';
}

// Get background class for site item based on status
function getStatusBgClass(status) {
    const bgClasses = {
        'starting': 'bg-blue-50',
        'finding_urls': 'bg-blue-50',
        'crawling': 'bg-blue-50',
        'completed': 'bg-green-50',
        'error': 'bg-red-50'
    };
    return bgClasses[status] || '';
}

// Format status for display
function formatStatus(status) {
    // Replace underscores with spaces and capitalize each word
    return status.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

// Delete a site
async function deleteSite(siteId, event) {
    event.stopPropagation();
    
    showConfirmation(
        'Delete Site',
        'Are you sure you want to delete this site? This will remove all its data from the database.',
        async () => {
            try {
                const response = await fetch(`/api/sites/${siteId}`, { method: 'DELETE' });
                if (!response.ok) throw new Error('Failed to delete site');
                // showToast('Site deleted'); // Toast handled by WebSocket now
                // loadSites(); // Handled by WebSocket now
            } catch (error) {
                console.error('Error deleting site:', error);
                showToast('Failed to delete site', 'error');
            }
        }
    );
}

// Clear the entire database
function confirmClearDatabase() {
    showConfirmation(
        'Clear Database',
        'This will delete ALL data from the database, including all sites and their content. This action cannot be undone.',
        async () => {
            try {
                const response = await fetch('/api/database', { method: 'DELETE' }); // Changed to DELETE
                if (!response.ok) throw new Error('Failed to clear database');
                // showToast('Database cleared'); // Toast handled by WebSocket now
                // loadSites(); // Handled by WebSocket now
                // chatMessages.innerHTML = `...`; // Handled by WebSocket now
            } catch (error) {
                console.error('Error clearing database:', error);
                showToast('Failed to clear database', 'error');
            }
        }
    );
}

// Show confirmation dialog
function showConfirmation(title, message, onConfirm) {
    modalTitle.textContent = title;
    modalMessage.textContent = message;
    
    // Remove previous event listeners
    const newBtn = confirmActionBtn.cloneNode(true);
    confirmActionBtn.parentNode.replaceChild(newBtn, confirmActionBtn);
    
    // Add new event listener
    newBtn.addEventListener('click', () => {
        closeModal();
        onConfirm();
    });
    
    // Update reference
    confirmActionBtn = newBtn;
    
    // Show modal
    confirmationModal.classList.remove('hidden');
}

// Close modal
function closeModal() {
    confirmationModal.classList.add('hidden');
}

// Toggle sources panel
function toggleSourcesPanel() {
    sourcesPanel.classList.toggle('hidden');
}

// Update sources in the side panel
function updateSources(sources) {
    if (!sources || sources.length === 0) {
        sourcesList.innerHTML = '<p class="text-sm text-gray-500">No sources found for this query.</p>';
        sourcesPanel.classList.add('hidden'); // Hide if no sources
        return;
    }
    
    sourcesList.innerHTML = `
        <h3 class="font-medium text-gray-700 mb-3">Sources (${sources.length})</h3>
        ${sources.map((source, index) => `
            <div class="source-item" onclick="window.open('${source.url}', '_blank')">
                <div class="source-title">
                    <i class="fas fa-link mr-2"></i>
                    ${source.title}
                </div>
                <div class="source-url" title="${source.url}">${source.url}</div>
                <div class="source-preview">${source.preview}</div>
            </div>
        `).join('')}
    `;
    
    // Show the panel if it's hidden
    if (sourcesPanel.classList.contains('hidden')) {
        toggleSourcesPanel();
    }
}

// Send a chat message
function sendMessage() {
    try {
        const message = userInput.value.trim();
        if (!message) return;
        
        // Add user message to chat
        appendMessage('user', message);
        userInput.value = '';
        
        // Disable input while waiting for response
        userInput.disabled = true;
        if (sendButton) sendButton.disabled = true;
        
        // Show typing indicator
        showTypingIndicator();
        
        // Send message via WebSocket
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({
                type: 'chat_message',
                content: message,
                message_id: `msg-${Date.now()}` // Client-side message ID
            }));
        } else {
            console.error('WebSocket is not connected');
            hideTypingIndicator();
            appendMessage('assistant', 'Error: Not connected to the server. Trying to reconnect...');
            
            // Try to reconnect
            connectWebSocket();
            
            // Re-enable input
            setTimeout(() => {
                userInput.disabled = false;
                if (sendButton) sendButton.disabled = false;
                userInput.focus();
            }, 1000);
        }
    } catch (error) {
        console.error('Error sending message:', error);
        hideTypingIndicator();
        showToast('Error sending message', 'error');
        userInput.disabled = false;
        if (sendButton) sendButton.disabled = false;
    }
}

// Initialize the application
function init() {
    try {
        // Initialize UI components
        initChatUI();
        
        // Load any existing sites
        loadSites();
        
        // Connect to WebSocket
        connectWebSocket();
        
        // Set up event listeners
        setupEventListeners();
        
        // Initial scroll to bottom
        setTimeout(scrollToBottom, 100);
        
        // Check for new messages periodically (for auto-scroll)
        setInterval(() => {
            if (isScrolledToBottom) {
                scrollToBottom('auto');
            }
        }, 1000);
        
    } catch (error) {
        console.error('Error initializing application:', error);
        showToast('Error initializing application', 'error');
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', init);

// Set up event listeners
function setupEventListeners() {
    // Send message on Enter key
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Toggle sources panel (event delegation for dynamic elements)
    document.addEventListener('click', (e) => {
        if (e.target.closest('.show-sources')) {
            toggleSourcesPanel();
        }
    });
}
