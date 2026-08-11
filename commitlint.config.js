module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Allow immutable bot-generated release/compare URLs without weakening commit headers.
    'body-max-line-length': [0],
    'footer-max-line-length': [0],
    'header-max-length': [2, 'always', 88]
  }
};
