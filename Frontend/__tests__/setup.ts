import { afterAll, afterEach, beforeAll } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom';

beforeAll(() => {});

afterEach(() => {
  cleanup();
});

afterAll(() => {});
