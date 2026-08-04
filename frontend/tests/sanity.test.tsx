import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/preact'

function Hello() {
  return <p>hello baduk</p>
}

describe('toolchain sanity', () => {
  it('renders a Preact component under Vitest+jsdom', () => {
    const { getByText } = render(<Hello />)
    expect(getByText('hello baduk')).toBeTruthy()
  })
})
