package com.hmdp.config;

import cn.hutool.core.util.StrUtil;
import org.redisson.Redisson;
import org.redisson.api.RedissonClient;
import org.redisson.config.Config;
import org.redisson.config.SingleServerConfig;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RedissonConfig {

    @Bean
    public RedissonClient redissonClient(@Value("${spring.redis.host}") String host,
                                         @Value("${spring.redis.port}") Integer port,
                                         @Value("${spring.redis.password:}") String password){
        // 配置
        Config config = new Config();
        SingleServerConfig singleServerConfig = config.useSingleServer()
                .setAddress("redis://" + host + ":" + port);
        if (StrUtil.isNotBlank(password)) {
            singleServerConfig.setPassword(password);
        }
        // 创建RedissonClient对象
        return Redisson.create(config);
    }
}
