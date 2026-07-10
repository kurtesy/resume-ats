import * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * Editorial Style Button Component
 *
 * Design Principles:
 * - Flat, no shadows
 * - Square corners (rounded-none)
 * - High contrast color inversion on hover
 * - Monochrome black/white palette with one semantic red for destructive actions
 */

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /**
   * Visual variant determining color and purpose:
   * - `default`: Black → white on hover - Primary actions (save, submit, create)
   * - `destructive`: Red → white on hover - Destructive actions (delete, remove)
   * - `outline`: White → black on hover - Secondary actions (cancel, back)
   * - `secondary`: Zinc-100 → zinc-200 on hover - Tertiary actions
   * - `ghost`: Transparent → gray - Subtle actions (icon buttons, navigation)
   * - `link`: Text only with underline - Inline links
   */
  variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link';
  /**
   * Button size:
   * - `default`: Standard button (h-10)
   * - `sm`: Small button (h-8)
   * - `lg`: Large button (h-12)
   * - `icon`: Square icon button (h-9 w-9)
   */
  size?: 'default' | 'sm' | 'lg' | 'icon';
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'default', ...props }, ref) => {
    // Base styles applied to ALL buttons
    // Swiss Design: clean, functional, high contrast
    const baseStyles = cn(
      // Layout & Typography
      'inline-flex items-center justify-center gap-2',
      'whitespace-nowrap text-sm font-medium font-mono uppercase tracking-wide',
      // Transitions
      'transition-all duration-150 ease-out',
      // Focus state - sharp black ring
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black focus-visible:ring-offset-2',
      // Disabled state
      'disabled:pointer-events-none disabled:opacity-50',
      // SVG icon sizing
      "[&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 [&_svg]:shrink-0",
      // Swiss Design: NO rounded corners
      'rounded-none'
    );

    // Variant styles - flat color inversion on hover
    const variants = {
      // PRIMARY - Pure Black
      // Use for: Save, Submit, Create, Primary CTA
      default: cn('bg-black text-white', 'border border-black', 'hover:bg-white hover:text-black'),

      // DESTRUCTIVE - Alert Red (only semantic color variant)
      // Use for: Delete, Remove, Destroy, Dangerous actions
      destructive: cn(
        'bg-red-600 text-white',
        'border border-red-600',
        'hover:bg-white hover:text-red-600'
      ),

      // OUTLINE - White background with black border
      // Use for: Cancel, Back, Secondary actions, Navigation
      outline: cn('bg-white text-black', 'border border-black', 'hover:bg-black hover:text-white'),

      // SECONDARY - Panel Grey
      // Use for: Less prominent actions, Toolbar buttons
      secondary: cn('bg-zinc-100 text-black', 'border border-black', 'hover:bg-zinc-200'),

      // GHOST - No background, minimal styling
      // Use for: Icon buttons, Subtle navigation, Toolbars
      ghost: cn(
        'bg-transparent text-black',
        'border-none shadow-none',
        'hover:bg-gray-100',
        'active:bg-gray-200'
      ),

      // LINK - Text only with underline
      // Use for: Inline links, Text navigation
      link: cn(
        'bg-transparent text-black',
        'border-none shadow-none',
        'underline-offset-4 hover:underline',
        'p-0 h-auto'
      ),
    };

    // Size styles
    const sizes = {
      default: 'h-10 px-6 py-2',
      sm: 'h-8 px-4 py-1 text-xs',
      lg: 'h-12 px-8 py-3 text-base',
      icon: 'h-10 w-10 p-0',
    };

    const variantClass = variants[variant];
    const sizeClass = sizes[size];

    return (
      <button ref={ref} className={cn(baseStyles, variantClass, sizeClass, className)} {...props} />
    );
  }
);
Button.displayName = 'Button';

export { Button };
