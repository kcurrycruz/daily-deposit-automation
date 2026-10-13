/* Close failed startup workers even when Tesseract's initialization promise stalls. */
'use strict';
const send = self.postMessage.bind(self);
self.postMessage = (message, ...options) => {
  send(message, ...options);
  if (message.status === 'reject' && ['load', 'loadLanguage', 'initialize'].includes(message.action)) {
    self.close();
  }
};
try {
  importScripts(new URL('./vendor/worker.min.js', self.location.href).href);
} catch (error) {
  self.close();
  throw error;
}
