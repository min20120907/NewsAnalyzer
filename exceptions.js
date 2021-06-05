function TargetExistedException(message, metadata) {
    const error = new Error(message);
    error.metadata = metadata;
    return error;
}
  
TargetExistedException.prototype = Object.create(Error.prototype);
