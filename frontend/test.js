const TurndownService = require('turndown');
const td = new TurndownService();
console.log(td.turndown('<img src="data:image/png;base64,abc" alt="test">'));
