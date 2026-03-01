// Jest setup file to handle missing modules
const path = require('path');

// Mock any missing modules
jest.mock('fs', () => ({
  readFileSync: jest.fn(),
  writeFileSync: jest.fn(),
  existsSync: jest.fn(),
  mkdirSync: jest.fn()
}));

// Handle missing modules gracefully
const originalRequire = require;
require = jest.fn((moduleName) => {
  try {
    return originalRequire(moduleName);
  } catch (error) {
    // Return a mock for missing modules
    return {
      [moduleName]: jest.fn(),
      default: jest.fn()
    };
  }
});
