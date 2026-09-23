self.addEventListener('push', function(event) {
    if (event.data) {
        let payload = {};
        try {
            payload = event.data.json();
        } catch(e) {
            payload = { message_preview: event.data.text() };
        }
        const sender = payload.sender_name || 'WhatsApp';
        const msg = payload.message_preview || 'You have a new message';
        const title = `${sender} (WhatsApp HR Inbox)`;
        const targetUrl = payload.url || '/app/whatsapp-hr-inbox' + (payload.conversation ? `?conversation=${payload.conversation}` : '');
        const options = {
            body: msg,
            icon: '/assets/frappe/images/frappe-framework-logo.svg',
            data: {
                url: targetUrl
            }
        };
        
        event.waitUntil(
            clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
                let isFocused = false;
                for (let i = 0; i < clientList.length; i++) {
                    let client = clientList[i];
                    if (client.url.includes('/whatsapp-hr-inbox') && client.focused) {
                        isFocused = true;
                        break;
                    }
                }
                if (!isFocused) {
                    return self.registration.showNotification(title, options);
                }
            })
        );
    }
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    
    const targetUrl = (event.notification.data && event.notification.data.url) || '/app/whatsapp-hr-inbox';
    
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            // First check if any window is already on whatsapp-hr-inbox
            for (let i = 0; i < clientList.length; i++) {
                let client = clientList[i];
                if (client.url.includes('whatsapp-hr-inbox') && 'focus' in client) {
                    client.focus();
                    if ('navigate' in client) {
                        return client.navigate(targetUrl);
                    }
                    return;
                }
            }
            // Next, focus and navigate any existing Frappe desk window
            for (let i = 0; i < clientList.length; i++) {
                let client = clientList[i];
                if ('focus' in client && 'navigate' in client) {
                    client.focus();
                    return client.navigate(targetUrl);
                }
            }
            // Fallback: open a new window
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
