/**
 * Decorative "false-color" spectral band, in the spirit of a 70s
 * scientific-poster heat map or a spectrograph read-out: cool violet/blue
 * bands shading into hot orange/white, with a bright scanning line
 * sweeping across it like an instrument taking a live reading.
 *
 * Purely decorative (aria-hidden) - it doesn't encode any real data, it's
 * the header's visual signature for the "Ultraviolet" theme. Animation is
 * pure CSS (see App.css `.spectral-hero__*`), so this component is just
 * markup - and disabled globally under prefers-reduced-motion (index.css).
 */
interface SpectralHeroProps {
  className?: string;
}

function SpectralHero({ className }: SpectralHeroProps) {
  const bands = [0, 1, 2, 3, 4, 5, 6];

  return (
    <svg
      className={className ? `spectral-hero ${className}` : "spectral-hero"}
      viewBox="0 0 800 84"
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id="spectral-hero-grad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="var(--color-violet)" />
          <stop offset="30%" stopColor="var(--color-uv-blue)" />
          <stop offset="55%" stopColor="var(--color-uv-cyan)" />
          <stop offset="80%" stopColor="var(--color-solar-orange)" />
          <stop offset="100%" stopColor="var(--color-white-hot)" />
        </linearGradient>
      </defs>

      {/* Seven bands, all sampling the same left-to-right spectral
          gradient - a rough, decorative stand-in for a thermal/false-color
          scan - each drifting horizontally out of phase with the others. */}
      {bands.map((row) => (
        <rect
          key={row}
          x="-80"
          y={row * 12}
          width="960"
          height="9"
          fill="url(#spectral-hero-grad)"
          opacity={0.5 + row * 0.06}
          className="spectral-hero__band"
          style={{ animationDelay: `${row * -1.1}s` }}
        />
      ))}

      {/* Bright scanning line, sweeping left to right like a live
          instrument reading. */}
      <rect
        x="0"
        y="0"
        width="26"
        height="84"
        fill="var(--color-white-hot)"
        className="spectral-hero__scan"
      />
    </svg>
  );
}

export default SpectralHero;
