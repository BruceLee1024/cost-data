import { forwardRef, type InputHTMLAttributes } from 'react'

const nativeInputTypes = new Set(['checkbox', 'file', 'radio'])

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className = '', type, ...props }, ref) => {
    const isNativeControl = type && nativeInputTypes.has(type)
    return <input ref={ref} type={type} className={isNativeControl ? className : `ui-input ${className}`.trim()} {...props} />
  },
)

Input.displayName = 'Input'
