console.log(JSON.stringify({ port: 54321, token: 'fake-token' }))
setInterval(() => {}, 1000) // держим процесс живым, как настоящий sidecar
