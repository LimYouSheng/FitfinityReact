import { useId } from 'react'

/** Render the original artwork with transparent dark pixels and theme-readable lettering. */
export default function BrandLogo({ className = '' }) {
  const id = useId()
  return <svg className={`brand-logo ${className}`.trim()} viewBox="0 0 1364 720" role="img" aria-label="OneFitfinity">
    <defs>
      <filter id={`${id}-clear`} colorInterpolationFilters="sRGB">
        <feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 1 1 1 0 0" />
        <feComponentTransfer><feFuncA type="table" tableValues="0 0 1 1 1 1 1 1 1 1 1" /></feComponentTransfer>
        <feComposite in="SourceGraphic" operator="in" />
      </filter>
      <clipPath id={`${id}-symbol`}><rect x="430" y="0" width="934" height="480" /></clipPath>
      <clipPath id={`${id}-words`}><rect x="0" y="0" width="430" height="480" /><rect x="0" y="480" width="1364" height="240" /></clipPath>
      <filter id={`${id}-light`} colorInterpolationFilters="sRGB">
        <feColorMatrix in="SourceGraphic" type="luminanceToAlpha" />
        <feComponentTransfer result="lettering"><feFuncA type="linear" slope="1.025" intercept="-0.025" /></feComponentTransfer>
        <feFlood floodColor="currentColor" />
        <feComposite operator="in" in2="lettering" />
      </filter>
    </defs>
    <image className="brand-logo-dark" href={`${import.meta.env.BASE_URL}assets/images/fitfinity-logo.jpg`} width="1364" height="720" filter={`url(#${id}-clear)`} />
    <image className="brand-logo-light" href={`${import.meta.env.BASE_URL}assets/images/fitfinity-logo.jpg`} width="1364" height="720" clipPath={`url(#${id}-symbol)`} filter={`url(#${id}-clear)`} />
    <image clipPath={`url(#${id}-words)`} className="brand-logo-light" href={`${import.meta.env.BASE_URL}assets/images/fitfinity-logo.jpg`} width="1364" height="720" filter={`url(#${id}-light)`} />
  </svg>
}
