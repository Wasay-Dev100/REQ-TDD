const path = require('path');

function render_register_page(req, res, locals = {}) {
  res.sendFile(path.join(__dirname, '../templates/user_registration_register.html'));
}

function render_verification_result_page(req, res, locals) {
  res.sendFile(path.join(__dirname, '../templates/user_registration_verification_result.html'));
}

module.exports = {
  render_register_page,
  render_verification_result_page
};