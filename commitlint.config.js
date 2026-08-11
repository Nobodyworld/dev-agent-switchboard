module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Dependency bots include immutable release and compare URLs longer than 100 characters.
    'body-max-line-length': [0],
    'footer-max-line-length': [0],
    'header-max-length': [2, 'always', 88]
  }
};
