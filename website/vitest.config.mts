import {defineConfig} from 'vitest/config';

// Docusaurus preserves JSX for its own build; rendered admin tests need it transformed.
export default defineConfig({oxc:{jsx:{runtime:'automatic'}}});
