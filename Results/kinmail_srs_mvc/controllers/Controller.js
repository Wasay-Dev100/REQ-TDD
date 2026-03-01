const express = require('express');
const { User } = require('../models/user');
const { EmailVerificationToken } = require('../models/user_registration_email_verification_token');
const { render_register_page, render_verification_result_page } = require('../views/user_registration_views');
const { validate_registration_payload, create_email_verification_token, send_verification_email } = require('./helper_functions');
const { TokenService } = require('../services/token_service');
const { EmailService } = require('../services/email_service');

const user_registration_bp = express.Router();

user_registration_bp.get('/register', async (req, res) => {
  await render_register_page(req, res);
});

user_registration_bp.post('/register', async (req, res) => {
  try {
    const payload = validate_registration_payload(req.body);
    const existingUser = await User.findOne({ where: { email: payload.email } });
    if (existingUser) {
      return res.status(409).json({ error: 'EMAIL_ALREADY_REGISTERED', message: 'Email is already registered.' });
    }

    const user = await User.create({
      email: payload.email,
      first_name: payload.first_name,
      last_name: payload.last_name,
      is_email_verified: false
    });
    await user.set_password(payload.password);

    const rawToken = TokenService.generate_raw_token();
    const tokenHash = TokenService.hash_token(rawToken);
    const token = await create_email_verification_token(user, tokenHash);

    await send_verification_email(user, rawToken);

    res.status(201).json({
      message: 'Registration successful. Please verify your email.',
      verification_email_sent: true
    });
  } catch (error) {
    if (error.name === 'ValidationError') {
      return res.status(400).json({ error: 'VALIDATION_ERROR', details: error.details });
    }
    res.status(500).json({ error: 'INTERNAL_SERVER_ERROR', message: 'An unexpected error occurred.' });
  }
});

user_registration_bp.get('/verify-email', async (req, res) => {
  const { token } = req.query;
  if (!token) {
    return render_verification_result_page(req, res, { verified: false, reason: 'MISSING_TOKEN' });
  }

  const tokenHash = TokenService.hash_token(token);
  const emailToken = await EmailVerificationToken.findOne({ where: { token_hash: tokenHash } });

  if (!emailToken || emailToken.is_expired() || emailToken.is_used()) {
    const reason = !emailToken ? 'INVALID_TOKEN' : emailToken.is_expired() ? 'TOKEN_EXPIRED' : 'TOKEN_USED';
    return render_verification_result_page(req, res, { verified: false, reason });
  }

  const user = await User.findOne({ where: { id: emailToken.user_id } });
  user.is_email_verified = true;
  await user.save();

  emailToken.mark_used();
  await emailToken.save();

  res.redirect(302, '/login');
});

module.exports = user_registration_bp;