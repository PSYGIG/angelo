# Angelo

## Commands

- **up** [service_name] - Starts service(s) based on the configuration file and connects to PSYGIG's platform if not already connected
- **down** [service_name] - Stops service(s) based on configuration file 
- **start** - Similar to up but only starts ALL services
- **stop** - Similar to down but stops ALL services and kills the connection to PSYGIG's platform
- **register** - Allows you to register the device on PSYGIG's platform (requires your application credentials)
- **reload** - Rereads the configuration file and restarts services based on the newly read configuration file
- **ps**/**top** - View status of services started by angelo

## Installation

If [available in Hex](https://hex.pm/docs/publish), the package can be installed
by adding `angelo` to your list of dependencies in `mix.exs`:

```elixir
def deps do
  [
    {:angelo, "~> 0.1.0"}
  ]
end
```

Documentation can be generated with [ExDoc](https://github.com/elixir-lang/ex_doc)
and published on [HexDocs](https://hexdocs.pm). Once published, the docs can
be found at [https://hexdocs.pm/angelo](https://hexdocs.pm/angelo).

