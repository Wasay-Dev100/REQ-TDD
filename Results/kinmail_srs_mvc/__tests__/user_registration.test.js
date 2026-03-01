import request from 'supertest';
import { app } from '../app';
import { User } from '../models/user';
import { EmailVerificationToken } from '../models/user_registration_email_verification_token';
import {
  validate_registration_payload,
  create_email_verification_token,
  send_verification_email,
} from '../controllers/user_registration_controller';

jest.mock('../services/email_service', () => {
  return {
    EmailService: jest.fn().mockImplementation(() => ({
      send_email: jest.fn().mockResolvedValue(undefined),
    })),
  };
});

jest.mock('../services/token_service', () => {
  return {
    TokenService: jest.fn().mockImplementation(() => ({
      generate_raw_token: jest.fn(() => 'raw_test_token_123'),
      hash_token: jest.fn((raw) => `hashed:${raw}`),
      timing_safe_equal: jest.fn((a, b) => a === b),
    })),
  };
});

const uniqueEmail = () => `test_${Date.now()}_${Math.floor(Math.random() * 1e9)}@example.com`;

describe('MODEL: User (models/user.py)', () => {
  test('test_user_model_has_required_fields', () => {
    expect(User).toBeDefined();
    expect(typeof User).toBe('function');

    const attrs = User.rawAttributes || User.getAttributes?.();
    expect(attrs).toBeDefined();

    expect(attrs).toHaveProperty('id');
    expect(attrs).toHaveProperty('email');
    expect(attrs).toHaveProperty('password_hash');
    expect(attrs).toHaveProperty('first_name');
    expect(attrs).toHaveProperty('last_name');
    expect(attrs).toHaveProperty('is_email_verified');
    expect(attrs).toHaveProperty('created_at');
    expect(attrs).toHaveProperty('updated_at');
  });

  test('test_user_set_password', async () => {
    const user = User.build({
      email: uniqueEmail(),
      first_name: 'John',
      last_name: 'Doe',
      password_hash: '',
      is_email_verified: false,
    });

    expect(user.set_password).toBeDefined();
    expect(typeof user.set_password).toBe('function');

    await expect(user.set_password('Password123!')).resolves.toBeUndefined();
    expect(user.password_hash).toBeTruthy();
    expect(user.password_hash).not.toBe('Password123!');
  });

  test('test_user_check_password', async () => {
    const user = User.build({
      email: uniqueEmail(),
      first_name: 'Jane',
      last_name: 'Doe',
      password_hash: '',
      is_email_verified: false,
    });

    await user.set_password('Password123!');
    expect(user.check_password).toBeDefined();
    expect(typeof user.check_password).toBe('function');

    await expect(user.check_password('Password123!')).resolves.toBe(true);
    await expect(user.check_password('WrongPassword!')).resolves.toBe(false);
  });

  test('test_user_unique_constraints', () => {
    const attrs = User.rawAttributes || User.getAttributes?.();
    expect(attrs).toBeDefined();
    expect(attrs.email).toBeDefined();

    const emailAttr = attrs.email;
    const isUnique =
      emailAttr.unique === true ||
      (typeof emailAttr.unique === 'string' && emailAttr.unique.length > 0) ||
      (emailAttr.unique && typeof emailAttr.unique === 'object');

    expect(isUnique).toBe(true);
  });
});

describe('MODEL: EmailVerificationToken (models/user_registration_email_verification_token.js)', () => {
  test('test_emailverificationtoken_model_has_required_fields', () => {
    expect(EmailVerificationToken).toBeDefined();
    expect(typeof EmailVerificationToken).toBe('function');

    const attrs = EmailVerificationToken.rawAttributes || EmailVerificationToken.getAttributes?.();
    expect(attrs).toBeDefined();

    expect(attrs).toHaveProperty('id');
    expect(attrs).toHaveProperty('user_id');
    expect(attrs).toHaveProperty('token_hash');
    expect(attrs).toHaveProperty('expires_at');
    expect(attrs).toHaveProperty('used_at');
    expect(attrs).toHaveProperty('created_at');
  });

  test('test_emailverificationtoken_is_expired', () => {
    const now = new Date();
    const past = new Date(now.getTime() - 60 * 1000);
    const future = new Date(now.getTime() + 60 * 60 * 1000);

    const tokenPast = EmailVerificationToken.build({
      user_id: 1,
      token_hash: `hashed:${uniqueEmail()}`,
      expires_at: past,
      used_at: null,
    });

    const tokenFuture = EmailVerificationToken.build({
      user_id: 1,
      token_hash: `hashed:${uniqueEmail()}`,
      expires_at: future,
      used_at: null,
    });

    expect(tokenPast.is_expired).toBeDefined();
    expect(typeof tokenPast.is_expired).toBe('function');
    expect(tokenPast.is_expired()).toBe(true);

    expect(tokenFuture.is_expired()).toBe(false);
  });

  test('test_emailverificationtoken_is_used', () => {
    const tokenUnused = EmailVerificationToken.build({
      user_id: 1,
      token_hash: `hashed:${uniqueEmail()}`,
      expires_at: new Date(Date.now() + 60 * 60 * 1000),
      used_at: null,
    });

    const tokenUsed = EmailVerificationToken.build({
      user_id: 1,
      token_hash: `hashed:${uniqueEmail()}`,
      expires_at: new Date(Date.now() + 60 * 60 * 1000),
      used_at: new Date(),
    });

    expect(tokenUnused.is_used).toBeDefined();
    expect(typeof tokenUnused.is_used).toBe('function');

    expect(tokenUnused.is_used()).toBe(false);
    expect(tokenUsed.is_used()).toBe(true);
  });

  test('test_emailverificationtoken_mark_used', () => {
    const token = EmailVerificationToken.build({
      user_id: 1,
      token_hash: `hashed:${uniqueEmail()}`,
      expires_at: new Date(Date.now() + 60 * 60 * 1000),
      used_at: null,
    });

    expect(token.mark_used).toBeDefined();
    expect(typeof token.mark_used).toBe('function');

    token.mark_used();
    expect(token.used_at).toBeInstanceOf(Date);
    expect(token.is_used()).toBe(true);
  });

  test('test_emailverificationtoken_unique_constraints', () => {
    const attrs = EmailVerificationToken.rawAttributes || EmailVerificationToken.getAttributes?.();
    expect(attrs).toBeDefined();
    expect(attrs.token_hash).toBeDefined();

    const tokenHashAttr = attrs.token_hash;
    const isUnique =
      tokenHashAttr.unique === true ||
      (typeof tokenHashAttr.unique === 'string' && tokenHashAttr.unique.length > 0) ||
      (tokenHashAttr.unique && typeof tokenHashAttr.unique === 'object');

    expect(isUnique).toBe(true);
  });
});

describe('ROUTE: /register (GET) - show_register', () => {
  test('test_register_get_exists', async () => {
    const res = await request(app).get('/register');
    expect([200, 302, 404, 405]).toContain(res.status);

    expect(res.status).not.toBe(404);
    expect(res.status).not.toBe(405);
  });

  test('test_register_get_renders_template', async () => {
    const res = await request(app).get('/register');
    expect(res.status).toBe(200);
    expect(res.headers['content-type']).toMatch(/text\/html/);
    expect(res.text).toBeTruthy();
  });
});

describe('ROUTE: /register (POST) - register', () => {
  test('test_register_post_exists', async () => {
    const res = await request(app)
      .post('/register')
      .set('Content-Type', 'application/json')
      .send({});

    expect([201, 400, 409, 500, 404, 405]).toContain(res.status);
    expect(res.status).not.toBe(404);
    expect(res.status).not.toBe(405);
  });

  test('test_register_post_success', async () => {
    const payload = {
      email: uniqueEmail(),
      password: 'Password123!',
      first_name: 'John',
      last_name: 'Doe',
    };

    const res = await request(app).post('/register').set('Content-Type', 'application/json').send(payload);

    expect(res.status).toBe(201);
    expect(res.headers['content-type']).toMatch(/application\/json/);
    expect(res.body).toEqual({
      message: 'Registration successful. Please verify your email.',
      verification_email_sent: true,
    });
  });

  test('test_register_post_missing_required_fields', async () => {
    const payload = {
      email: uniqueEmail(),
      password: 'Password123!',
      first_name: 'John',
    };

    const res = await request(app).post('/register').set('Content-Type', 'application/json').send(payload);

    expect(res.status).toBe(400);
    expect(res.headers['content-type']).toMatch(/application\/json/);
    expect(res.body).toHaveProperty('error', 'VALIDATION_ERROR');
    expect(Array.isArray(res.body.details)).toBe(true);
    expect(res.body.details.length).toBeGreaterThan(0);
    for (const item of res.body.details) {
      expect(item).toHaveProperty('field');
      expect(item).toHaveProperty('message');
    }
  });

  test('test_register_post_invalid_data', async () => {
    const payload = {
      email: 'not-an-email',
      password: 'short',
      first_name: '',
      last_name: '',
      extra: 'not allowed',
    };

    const res = await request(app).post('/register').set('Content-Type', 'application/json').send(payload);

    expect(res.status).toBe(400);
    expect(res.headers['content-type']).toMatch(/application\/json/);
    expect(res.body).toHaveProperty('error', 'VALIDATION_ERROR');
    expect(Array.isArray(res.body.details)).toBe(true);
    expect(res.body.details.length).toBeGreaterThan(0);
  });

  test('test_register_post_duplicate_data', async () => {
    const email = uniqueEmail();
    const payload = {
      email,
      password: 'Password123!',
      first_name: 'John',
      last_name: 'Doe',
    };

    const res1 = await request(app).post('/register').set('Content-Type', 'application/json').send(payload);
    expect([201, 409]).toContain(res1.status);

    const res2 = await request(app).post('/register').set('Content-Type', 'application/json').send(payload);

    expect(res2.status).toBe(409);
    expect(res2.headers['content-type']).toMatch(/application\/json/);
    expect(res2.body).toHaveProperty('error', 'EMAIL_ALREADY_REGISTERED');
    expect(res2.body).toHaveProperty('message');
    expect(typeof res2.body.message).toBe('string');
    expect(res2.body.message.length).toBeGreaterThan(0);
  });
});

describe('ROUTE: /verify-email (GET) - verify_email', () => {
  test('test_verify_email_get_exists', async () => {
    const res = await request(app).get('/verify-email');
    expect([302, 400, 404, 405]).toContain(res.status);

    expect(res.status).not.toBe(404);
    expect(res.status).not.toBe(405);
  });

  test('test_verify_email_get_renders_template', async () => {
    const res = await request(app).get('/verify-email');
    expect(res.status).toBe(400);
    expect(res.headers['content-type']).toMatch(/text\/html/);
    expect(res.text).toBeTruthy();
  });
});

describe('HELPER: validate_registration_payload([object Object])', () => {
  test('test_validate_registration_payload_function_exists', () => {
    expect(validate_registration_payload).toBeDefined();
    expect(typeof validate_registration_payload).toBe('function');
  });

  test('test_validate_registration_payload_with_valid_input', () => {
    const payload = {
      email: uniqueEmail(),
      password: 'Password123!',
      first_name: 'John',
      last_name: 'Doe',
    };

    const result = validate_registration_payload(payload);
    expect(result).toBeDefined();
    expect(typeof result).toBe('object');
  });

  test('test_validate_registration_payload_with_invalid_input', () => {
    const payload = {
      email: 'bad',
      password: 'short',
      first_name: '',
      last_name: '',
      extra: 'nope',
    };

    const result = validate_registration_payload(payload);
    expect(result).toBeDefined();
    expect(typeof result).toBe('object');
  });
});

describe('HELPER: create_email_verification_token([object Object])', () => {
  test('test_create_email_verification_token_function_exists', () => {
    expect(create_email_verification_token).toBeDefined();
    expect(typeof create_email_verification_token).toBe('function');
  });

  test('test_create_email_verification_token_with_valid_input', async () => {
    const user = User.build({
      id: 123,
      email: uniqueEmail(),
      first_name: 'John',
      last_name: 'Doe',
      password_hash: 'hash',
      is_email_verified: false,
    });

    const token = await create_email_verification_token(user);
    expect(token).toBeDefined();
    expect(token).toBeInstanceOf(EmailVerificationToken);

    expect(token.user_id).toBeDefined();
    expect(token.token_hash).toBeDefined();
    expect(token.expires_at).toBeDefined();
  });

  test('test_create_email_verification_token_with_invalid_input', async () => {
    await expect(create_email_verification_token(null)).rejects.toBeDefined();
  });
});

describe('HELPER: send_verification_email([object Object], [object Object])', () => {
  test('test_send_verification_email_function_exists', () => {
    expect(send_verification_email).toBeDefined();
    expect(typeof send_verification_email).toBe('function');
  });

  test('test_send_verification_email_with_valid_input', async () => {
    const user = User.build({
      id: 456,
      email: uniqueEmail(),
      first_name: 'John',
      last_name: 'Doe',
      password_hash: 'hash',
      is_email_verified: false,
    });

    await expect(send_verification_email(user, 'raw_test_token_123')).resolves.toBeUndefined();
  });

  test('test_send_verification_email_with_invalid_input', async () => {
    const user = User.build({
      id: 789,
      email: uniqueEmail(),
      first_name: 'John',
      last_name: 'Doe',
      password_hash: 'hash',
      is_email_verified: false,
    });

    await expect(send_verification_email(null, 'raw_test_token_123')).rejects.toBeDefined();
    await expect(send_verification_email(user, null)).rejects.toBeDefined();
  });
});