export function setupCounter(element: HTMLButtonElement) {
  let counter = 0
  // Tiny Vite starter helper. Kept only because file still exists in template.
  const setCounter = (count: number) => {
    counter = count
    element.innerHTML = `Count is ${counter}`
  }
  element.addEventListener('click', () => setCounter(counter + 1))
  setCounter(0)
}
