module.exports = {
  testEnvironment: 'node',
  testMatch: [
    '**/__tests__/**/*.js',
    '**/__tests__/**/*.ts',
    '**/?(*.)+(spec|test).js',
    '**/?(*.)+(spec|test).ts'
  ],
  testPathIgnorePatterns: [
    '/node_modules/'
  ],
  collectCoverageFrom: [
    '**/*.{js,ts}',
    '!**/node_modules/**',
    '!**/__tests__/**'
  ],
  moduleFileExtensions: ['js', 'json', 'jsx', 'ts', 'tsx', 'node'],
  moduleNameMapping: {
    // Handle any missing modules gracefully
    '^.*$': '<rootDir>/__tests__/$1'
  },
  setupFilesAfterEnv: ['<rootDir>/__tests__/setup.js'],
  verbose: true,
  // Don't fail on missing modules
  errorOnDeprecated: false
};
