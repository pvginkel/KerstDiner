/**
 * Button variant and size class maps — app-owned, customizable per project.
 * KerstDiner's are festive: red, green and cream, with a gold rim, and big
 * enough to tap on a phone.
 */

export const buttonBaseClasses = {
  default: 'inline-flex items-center justify-center whitespace-nowrap rounded-full font-extrabold transition focus-visible:outline-hidden focus-visible:ring-4 focus-visible:ring-kerst-gold-light disabled:pointer-events-none disabled:opacity-50 active:scale-[0.98] cursor-pointer',
  filter: 'inline-flex items-center justify-center whitespace-nowrap rounded-full font-semibold transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 cursor-pointer',
} as const;

export const buttonVariants = {
  default: 'border-[3px] border-kerst-gold bg-primary text-primary-foreground shadow-[0_4px_0_var(--color-kerst-red-dark)] hover:bg-primary/90',
  primary: 'border-[3px] border-kerst-gold bg-primary text-primary-foreground shadow-[0_4px_0_var(--color-kerst-red-dark)] hover:bg-primary/90',
  secondary: 'border-[3px] border-kerst-gold bg-secondary text-secondary-foreground shadow-[0_4px_0_var(--color-kerst-pine)] hover:bg-secondary/90',
  outline: 'border-[3px] border-kerst-gold bg-card text-card-foreground hover:bg-accent/40',
  ghost: 'hover:bg-accent/40 hover:text-accent-foreground',
  ai_assisted: 'bg-gradient-to-r from-[#0afecf] to-[#16bbd4] ai-glare',
  filter: 'border border-input bg-background text-foreground hover:opacity-80 aria-pressed:bg-primary aria-pressed:text-primary-foreground aria-pressed:border-primary',
  destructive: 'border-[3px] border-kerst-gold bg-destructive text-destructive-foreground hover:bg-destructive/90',
} as const;

export const buttonSizes = {
  default: {
    sm: 'h-9 px-3 text-sm',
    md: 'h-12 px-5 text-base',
    lg: 'h-14 px-8 text-lg',
  },
  filter: {
    sm: 'px-2.5 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
    lg: 'px-4 py-1.5 text-base',
  },
} as const;

/** Text gradient classes for the ai_assisted variant's children. */
export const buttonAiTextClasses = 'bg-gradient-to-r from-[#1982a4] to-[#bd3cb9] bg-clip-text text-transparent relative z-10';
