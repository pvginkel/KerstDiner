import { createRouter, RouterProvider } from '@tanstack/react-router'

// Import the generated route tree
import { routeTree } from './routeTree.gen'
import { isTestMode } from '@/lib/config/test-mode'
import { setupRouterInstrumentation } from '@/lib/test/router-instrumentation'
import { CorrelationProvider } from '@/contexts/correlation-context'
import { registerPublicRouteCheck } from '@/lib/auth-redirect'

// Create a new router instance
const router = createRouter({ routeTree })

// The API client's 401-to-login redirect skips a public route. It asks the
// router about the location it is on or going to, whose matches may not have
// loaded yet.
registerPublicRouteCheck(() => {
  const [matchedRoutes] = router.getMatchedRoutes(router.latestLocation.pathname)
  return matchedRoutes.some((route) => route.options.staticData?.public === true)
})

// Setup router instrumentation in test mode
if (isTestMode()) {
  setupRouterInstrumentation(router);
}

// Register the router instance for type safety
declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

function App() {
  return (
    <CorrelationProvider>
      <RouterProvider router={router} />
    </CorrelationProvider>
  )
}

export default App
