/**
 * BackoffController coordinates exponential backoff with jitter for reconnect attempts.
 *
 * Options:
 * - initialDelayMs (number): Base delay in milliseconds for the first retry.
 * - maxDelayMs (number): Upper bound for the delay after applying multiplier and jitter.
 * - multiplier (number): Exponential multiplier applied per attempt (> 0).
 * - jitterRatio (number): Fractional jitter window (e.g., 0.2 => ±20%).
 * - minDelayMs (number): Hard lower bound for jittered delays (defaults to initialDelayMs).
 * - random (function): RNG returning a float in [0, 1]; defaults to Math.random.
 */
export class BackoffController {
  constructor(options = {}) {
    const {
      initialDelayMs = 2000,
      maxDelayMs = 30000,
      multiplier = 2,
      jitterRatio = 0.2,
      minDelayMs = undefined,
      random = Math.random,
    } = options;

    this._initialDelayMs = BackoffController._validatePositiveNumber(initialDelayMs, 'initialDelayMs');
    this._maxDelayMs = BackoffController._validatePositiveNumber(maxDelayMs, 'maxDelayMs');
    this._multiplier = BackoffController._validatePositiveNumber(multiplier, 'multiplier');
    this._jitterRatio = BackoffController._validateNonNegativeNumber(jitterRatio, 'jitterRatio');
    this._minDelayMs = minDelayMs === undefined
      ? this._initialDelayMs
      : BackoffController._validatePositiveNumber(minDelayMs, 'minDelayMs');

    if (this._maxDelayMs < this._minDelayMs) {
      throw new Error('maxDelayMs must be greater than or equal to minDelayMs');
    }

    if (typeof random !== 'function') {
      throw new Error('random must be a function');
    }

    this._random = random;
    this._attempts = 0;
  }

  static _validatePositiveNumber(value, name) {
    if (!Number.isFinite(value) || value <= 0) {
      throw new Error(`${name} must be a positive finite number`);
    }
    return value;
  }

  static _validateNonNegativeNumber(value, name) {
    if (!Number.isFinite(value) || value < 0) {
      throw new Error(`${name} must be a non-negative finite number`);
    }
    return value;
  }

  get attempts() {
    return this._attempts;
  }

  reset() {
    this._attempts = 0;
  }

  nextDelay() {
    this._attempts += 1;

    const exponent = this._attempts - 1;
    const exponential = this._initialDelayMs * Math.pow(this._multiplier, exponent);
    const baseDelay = Math.min(exponential, this._maxDelayMs);

    if (this._jitterRatio <= 0) {
      return Math.round(baseDelay);
    }

    const jitter = baseDelay * this._jitterRatio;
    const minDelay = Math.max(this._minDelayMs, baseDelay - jitter);
    const maxDelay = Math.max(minDelay, baseDelay + jitter);

    const randomValueRaw = this._random();
    const randomValue = Math.min(Math.max(Number(randomValueRaw) || 0, 0), 1);
    const jittered = minDelay + randomValue * (maxDelay - minDelay);

    return Math.round(jittered);
  }
}

export default BackoffController;
