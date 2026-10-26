/** Tailwind is prefixed to avoid collisions with Bootstrap utility class names. */
module.exports = {
  prefix: 'tw-',
  content: ['./templates/**/*.html', './static/js/**/*.js'],
  corePlugins: { preflight: false },
  theme: { extend: { colors: { ink: '#101e33', paper: '#f6f8fc', brand: '#3476e7' } } },
  plugins: [],
};
