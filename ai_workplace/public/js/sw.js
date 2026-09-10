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
        const title = `${sender}: ${msg}`;
        const options = {
            body: 'HR Inbox',
            icon: '/assets/frappe/images/frappe-framework-logo.svg',
            data: {
                url: payload.url || '/app/whatsapp-hr-inbox'
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
    
    if (event.notification.data && event.notification.data.url) {
        event.waitUntil(
            clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
                for (let i = 0; i < clientList.length; i++) {
                    let client = clientList[i];
                    if (client.url.includes('/whatsapp-hr-inbox') && 'focus' in client) {
                        return client.focus();
                    }
                }
                if (clients.openWindow) {
                    return clients.openWindow(event.notification.data.url);
                }
            })
        );
    }
});
