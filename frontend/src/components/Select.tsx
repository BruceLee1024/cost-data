import { forwardRef, type SelectHTMLAttributes } from 'react'

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className = '', children, ...props }, ref) => (
    <select ref={ref} className={`ui-select ${className}`.trim()} {...props}>
      {children}
    </select>
  ),
)

Select.displayName = 'Select'
