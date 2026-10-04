const initialState = Object.freeze({
  brief: null,
  sourceUrl: '',
  activeJob: null,
  error: null,
});

export function reducer(state, action) {
  switch (action.type) {
    case 'SOURCE_SELECTED':
      return {...state, sourceUrl: action.url || ''};
    case 'JOB_UPDATED':
      return {...state, activeJob: action.job, error: null};
    case 'BRIEF_LOADED':
      return {...state, brief: action.brief, sourceUrl: action.brief.url || state.sourceUrl, error: null};
    case 'FAILED':
      return {...state, error: action.error, activeJob: null};
    case 'RESET_INPUT':
      return {...state, error: null};
    default:
      return state;
  }
}

export function createStore(reduce = reducer, seed = initialState) {
  let state = seed;
  const listeners = new Set();
  return {
    getState: () => state,
    dispatch(action) {
      const previous = state;
      state = reduce(state, action);
      listeners.forEach(listener => listener(state, previous, action));
      return action;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
