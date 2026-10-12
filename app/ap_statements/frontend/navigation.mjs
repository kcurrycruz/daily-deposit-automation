export function backButtonHtml() {
  return '<button type="button" class="program-back" data-action="back-to-programs"><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M19 12H5m6-6-6 6 6 6"/></svg><span>Go back to programs</span></button>';
}

export function requestProgramHub(target, confirmed = false) {
  if (confirmed === true) target.dispatchEvent(new Event('hwfc:return-to-programs'));
}
